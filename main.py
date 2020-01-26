import logging
import logging.config
import sys
import json
import csv
import os

from reyaml import load_from_file
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    Filters,
)
from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup, ParseMode
from telegram.ext.dispatcher import run_async

from structures import Route, Transport
import constants as c
import keyboards as k
from mqtt_client import MqttClient
import restapi

logging.config.fileConfig("logging.conf")

log = logging.getLogger("infobot")


class Infobot:
    def __init__(self, mqtt, bot, config):
        """Constructor
        :param mqtt: instance of MqttClient object
        :param bot: instance of Telegram bot object
        :param config: dict, the raw config (normally loaded from YAML)"""
        self.mqtt = mqtt
        self.bot = bot
        self.rest = None  # REST API, will be initialized in self.serve
        self.config = config

        self.predictions = {}
        self.stations = None

        # the key will be a string with the route name, and the value will be Route objects
        self.routes = {}

        # This dict maps {station_id: station_name} for all routes, as some stations are
        # shared between them, so they're all in one namespace.
        self.all_stations = {}

        # this dict will contain Transport objects, the key will be the route
        # name, the value is the object itself, reflecting the last known
        # state of this transport unit
        # TODO should be an expiring dict, as at some point a trolleybus will
        # be taken offline (we won't receive a notification about it), yet the
        # system will think it still belongs to that route.
        self.transports = {}

        self.feedback_chat_id = self.config["telegram"]["feedback_chat_id"]

    def refresh_transport(self, data):
        """Update the state info of a given transport
        :param data: dict, the metadata about the transport whereabouts, the keys
                     are:  rtu_id, board, route, lat, lon, speed, dir"""
        try:
            transport = self.transports[data["board"]]
        except KeyError:
            transport = Transport()
            transport.board_name = data["board"]
            transport.rtu_id = data["rtu_id"]

            self.transports[data["board"]] = transport

        transport.latitude = data["lat"]
        transport.longitude = data["lon"]
        transport.speed = data["speed"]
        transport.direction = data["dir"]
        # contrary to common sense, the route can change throughout the day,
        # so we cannot count on it being constant, thus we overwrite this
        # value each time, just in case
        transport.route = data["route"]
        try:
            transport.last_station_order = data["last_station"]
        except KeyError:
            # the key isn't there, it means the backend doesn't have this info
            # yet. We ignore it for now, the info will be here within a few iterations
            pass

    def load_route(self, path, route_name):
        """Load route data from the given CSV file
        :param path: str, full path to CSV file
        :param route_name: str, human-readable name of the route"""
        segments = []
        last_segment = ""
        cutoff_station_id = None
        station_sequence = []

        with open(path) as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # skip header
            for station_id, station_order, station_name, segment, *rest in reader:
                station_id = int(station_id)
                station_order = int(station_order)
                # determine what the segments are and the cut-off point
                if last_segment and last_segment != segment:
                    cutoff_station_id = station_id
                else:
                    if segment not in segments:
                        segments.append(segment)
                last_segment = segment

                # here we grow the sequence of stations for the given route
                station_sequence.append(station_id)

                # update the global dictionary of all station IDs and their names
                self.all_stations[station_id] = station_name

        result = Route(route_name, segments, cutoff_station_id, station_sequence)
        return result

    def preload_structures(self):
        """Load information about routes from the available resource files"""
        log.debug("Loading station data")
        for entry in os.listdir("res/routes"):
            route_name, _extension = os.path.splitext(entry)
            route = self.load_route(os.path.join("res/routes", entry), route_name)
            self.routes[route_name] = route
            self.predictions[route_name] = {}
        log.info(
            "Loaded %i routes: %s", len(self.routes), sorted(list(self.routes.keys()))
        )

    def serve(self):
        """The main loop"""
        self.preload_structures()

        # MQTT's loop won't block, it runs in a separate thread
        self.mqtt.set_external_handler(self.on_mqtt)
        self.mqtt.client.subscribe(
            [
                ("state/station/+", c.QOS_EXACTLY_ONCE),
                ("state/transport/+", c.QOS_EXACTLY_ONCE),
            ]
        )
        self.mqtt.client.loop_start()

        log.info("Starting REST API in separate thread")
        self.rest = restapi.BotRestApi(self.send_message_hook)
        restapi.run_background(self.rest)

        log.info("Starting Telegram bot")
        self.init_bot()
        self.bot.start_polling()
        self.bot.idle()

    @staticmethod
    def get_params(raw):
        """Retrieve the parameters that were transmitted along with the
        command, if any.
        :param raw: str, the raw text sent by the user"""
        parts = raw.split(" ", 1)
        return None if len(parts) == 1 else parts[1]

    def form_digest_markdown(self, route, station_id=None):
        """Form a digest of ETAs for a given route and optionally, a station_id
        :param route: str, route number/name
        :param station_id: int, optional, station for which you want the data"""
        if station_id is not None:
            data = self.predictions[route][station_id]
            return str(data)

        # otherwise it is a request for the whole list of stations, we start
        # with the name of the first segment of the route
        result = """*%s*\n""" % self.routes[route].segments[0]

        last_prognosis = None
        for station_id in self.routes[route].station_sequence:
            if station_id == self.routes[route].cutoff_station_id:
                # for easier readability, we add the header for the return part
                # of the route
                result += "\n*%s*\n" "" % self.routes[route].segments[1]

            station_name = self.all_stations[station_id]
            etas = self.predictions[route].get(station_id, [])
            if not etas:
                result += f"{station_name}: 🚫\n"
                continue

            string_etas = ", ".join([str(item) for item in etas])
            current_prognosis = etas[0]
            if current_prognosis == 0 and last_prognosis != 0:
                # it means the trolleybus is there right now, let's add a
                # trolleybus icon, for a better effect
                # however, there is another condition - there must be no
                # stretch of 0 ETAs. When the stations are close to each
                # other, they can both have a legit "0 minutes" ETA, but
                # only the first entry can realistically be the place where
                # the transport is right now.
                result += f"{c.ICON_BUS} {station_name}: {string_etas}\n"
            else:
                if (
                    last_prognosis is not None
                    and last_prognosis != 0
                    and current_prognosis < last_prognosis
                ):
                    # it means we're dealing with the case where the transport is
                    # between stations, so we render a bus icon between stations
                    result += f"{c.ICON_BUS} \n"
                result += f"{station_name}: {string_etas}\n"
            last_prognosis = current_prognosis

        return result

    @staticmethod
    def on_bot_start(update, context):
        """Send a message when the command /start is issued."""
        user = update.effective_user
        log.info(
            f"ADD {user.username}, {user.full_name}, @{update.effective_chat.id}, {user.language_code}"
        )
        update.message.reply_text(
            f"Bine ai venit, {user.username or user.full_name}. Roata v{c.VERSION} te ascultă!"
            f"\n Comanda /help îți va arăta ce pot face și va explica "
            f"cum să interpretezi răspunsurile mele.\n\n{c.MSG_HELP}"
        )
        update.message.reply_text(
            f"Nu uita să povestești colegilor despre mine. Rrrroata wăy!!!"
        )

        context.bot.sendMessage(
            chat_id=update.message.chat_id,
            text="test",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardMarkup(k.default_board, one_time_keyboard=True),
        )

    def on_bot_prognosis(self, update, context):
        """Send a message when the command /prognosis is issued."""
        user = update.effective_user
        raw_text = update.message.text
        log.info(
            f"REQ from [{user.username or user.full_name} @{update.effective_chat.id}]: {raw_text}"
        )

        route = self.get_params(raw_text)
        if route is None:
            # show 'em the keyboard to ask them to select a route from a list, by
            # pressing a button
            routes_board = k.build_route_menu(sorted(self.routes.keys()))
            reply_markup = InlineKeyboardMarkup(routes_board)
            update.message.reply_text(c.MSG_CHOOSE_ROUTE, reply_markup=reply_markup)
        else:
            if route not in self.routes:
                update.message.reply_text(c.MSG_UNSUPPORTED_ROUTE)
                return

            etas = self.form_digest_markdown(route)
            context.bot.sendMessage(
                chat_id=update.message.chat_id, text=etas, parse_mode=ParseMode.MARKDOWN
            )

            nudges = c.MSG_MAP + '\n' + c.MSG_FEEDBACK_NUDGE
            context.bot.sendMessage(
                chat_id=update.message.chat_id,
                text=nudges,
                parse_mode=ParseMode.HTML,
                disable_notification=True,
                disable_web_page_preview=True,
            )

    @staticmethod
    def on_bot_help(update, context):
        """Send a message when the command /help is issued."""
        update.message.reply_text(c.MSG_HELP)
        update.message.reply_text(c.MSG_SAMPLE)
        update.message.reply_photo(photo=open("res/help-screenshot.png", "rb"))

    @staticmethod
    def on_bot_about(update, context):
        """Send a message when the command /about is issued."""
        update.message.reply_text(c.MSG_ABOUT)

    @staticmethod
    def on_bot_feedback(update, context):
        """Send a message when the command /feeedback is issued."""
        update.message.reply_text(c.MSG_FEEDBACK)
        return c.STATE_EXPECTING_FEEDBACK

    def on_bot_feedback_received(self, update, context):
        """Send a message when the command /feeedback is issued."""
        user = update.message.from_user
        raw_text = update.message.text
        log.info(f"FEED from [{user.username} @{update.effective_chat.id}]: {raw_text}")
        update.message.reply_text(c.MSG_THANKS)

        report = f"FEED from [{user.username or user.full_name} @{update.effective_chat.id}]: {raw_text}"
        context.bot.sendMessage(chat_id=self.feedback_chat_id, text=report)
        return ConversationHandler.END

    @staticmethod
    def on_bot_feedback_cancel(update, context):
        update.message.reply_text(c.MSG_FEEDBACK_CANCELLED)
        return ConversationHandler.END

    @staticmethod
    def on_bot_reply(update, context):
        """Send a message when the command /reply is issued."""
        update.message.reply_text(c.MSG_REPLY_HINT)
        return c.STATE_EXPECTING_REPLY

    def on_bot_reply_received(self, update, context):
        """Send a message when the command /reply is issued and we received a reply."""
        user = update.message.from_user
        raw_text = update.message.text
        log.info(
            f"REPLY from [{user.username} @{update.effective_chat.id}]: {raw_text}"
        )

        report = f"REPLY from [{user.username or user.full_name}]: {raw_text}"
        context.bot.sendMessage(chat_id=self.feedback_chat_id, text=report)
        return ConversationHandler.END

    @staticmethod
    def on_bot_reply_cancel(update, context):
        return ConversationHandler.END

    @staticmethod
    def on_bot_error(update, context):
        """Log Errors caused by Updates."""
        log.warning('Update "%s" caused error "%s"', update, context.error)

    def init_bot(self):
        dispatcher = self.bot.dispatcher

        dispatcher.add_handler(CommandHandler("start", self.on_bot_start))
        dispatcher.add_handler(CommandHandler("help", self.on_bot_help))
        dispatcher.add_handler(CommandHandler("prognosis", self.on_bot_prognosis))
        dispatcher.add_handler(CommandHandler("about", self.on_bot_about))
        dispatcher.add_handler(self.feedback_handler())
        dispatcher.add_handler(self.reply_handler())
        dispatcher.add_handler(CallbackQueryHandler(self.on_bot_route_button))
        dispatcher.add_error_handler(self.on_bot_error)

    def feedback_handler(self):
        """This creates a conversation in which we ask the user to provide feedback"""
        handler = ConversationHandler(
            entry_points=[CommandHandler("feedback", self.on_bot_feedback)],
            states={
                c.STATE_EXPECTING_FEEDBACK: [
                    MessageHandler(Filters.text, self.on_bot_feedback_received)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.on_bot_feedback_cancel)],
        )
        return handler

    def reply_handler(self):
        """This creates a conversation in which we interact with a user who provided feedback"""
        handler = ConversationHandler(
            entry_points=[CommandHandler("reply", self.on_bot_reply)],
            states={
                c.STATE_EXPECTING_REPLY: [
                    MessageHandler(Filters.text, self.on_bot_reply_received)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.on_bot_reply_cancel)],
        )
        return handler

    def on_bot_route_button(self, update, context):
        """Invoked when they sent /prognosis without a parameter, then clicked
        a button from the list of routes"""
        query = update.callback_query
        route = query.data
        user = update.effective_user
        log.info(
            f"REQ from [{user.username or user.full_name} @{update.effective_chat.id}]: /prognosis {route} via kboard"
        )

        etas = self.form_digest_markdown(route)
        context.bot.sendMessage(
            chat_id=query.message.chat_id,
            text=etas,
            parse_mode=ParseMode.MARKDOWN,
            disable_notification=True,
        )

        nudges = c.MSG_MAP + '\n' + c.MSG_FEEDBACK_NUDGE
        context.bot.sendMessage(
            chat_id=query.message.chat_id,
            text=nudges,
            parse_mode=ParseMode.HTML,
            disable_notification=True,
            disable_web_page_preview=True,
        )

    def on_mqtt(self, client, userdata, msg):
        log.debug(
            "MQTT IN %s %i bytes `%s`", msg.topic, len(msg.payload), repr(msg.payload)
        )
        try:
            data = json.loads(msg.payload)
        except ValueError:
            log.debug("Ignoring bad MQTT data %s", repr(msg.payload))
            return

        if "station" in msg.topic:
            # we're dealing with data concerning ETA predictions
            route = list(data["eta"].keys())[0]
            station_id = data["station_id"]
            if route not in self.predictions:
                # if this route is not yet in our state dict, add it
                self.predictions[route] = {}

            # first, we discard the information about the board numbers, as we won't use it
            # here, we extract just the ETAs
            predictions = [eta for eta, board in data["eta"][route]]

            # sometimes there are dupes, so we turn them into a set, to filter those dupes
            predictions = sorted(list(set(predictions)))

            # if len(predictions) == 1 and predictions[0] == 0:
            #     # at the end of the day, we end up with something that looks like a zero
            #     # prognosis, but actually it is a `void` situation, when no data are available
            #     predictions = []
            self.predictions[route][station_id] = predictions

        elif "transport" in msg.topic:
            # we're dealing with location data about the whereabouts of a trolleybus. The
            # data is a dict with the following keys: rtu_id, board, route, lat, lon, speed, dir
            self.refresh_transport(data)

    @run_async
    def send_message_hook(self, chat_id, text):
        """This will be invoked by the REST API when the sysadmin wants to
        send a message back to a user who left feedback via /feedback and
        asked a question, which expects a response
        :param chat_id: int, chat identifier
        :param text: str, the text to be sent to the user"""
        self.bot.bot.sendMessage(chat_id=chat_id, text=text + c.MSG_REPLY)
        log.info("Sendweb @%s: %s", chat_id, text)


if __name__ == "__main__":
    log.info("Starting Infobot v%s", c.VERSION)

    config_path = sys.argv[-1]

    log.info("Processing config from `%s`", config_path)
    config = load_from_file(config_path)

    mqtt_conf = config["mqtt"]
    mqtt = MqttClient(
        name="infobot",
        broker=mqtt_conf["host"],
        port=mqtt_conf["port"],
        username=mqtt_conf["username"],
        password=mqtt_conf["password"],
    )
    bot = Updater(token=config["telegram"]["token"], use_context=True)
    infobot = Infobot(mqtt, bot, config)

    try:
        infobot.serve()
    except KeyboardInterrupt:
        log.debug("Interactive quit")
        sys.exit()
    finally:
        log.info("Quitting")
