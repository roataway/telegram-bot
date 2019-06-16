import logging
from threading import Thread

from werkzeug.wrappers import Request, Response
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import BadRequest, MethodNotAllowed, HTTPException

log = logging.getLogger("rest")


class BotRestApi(object):
    def __init__(self, messageFun):
        """Initialize the REST API
        :param messageFun: callable, a function that will be invoked when a message was sent via the web-ui"""
        self.messageFun = messageFun
        self.form = open("res/static/chatform.html", "rb").read()
        self.url_map = Map(
            [Rule("/", endpoint="root"), Rule("/message", endpoint="message")]
        )

    def dispatch_request(self, request):
        adapter = self.url_map.bind_to_environ(request.environ)
        try:
            endpoint, values = adapter.match()
            return getattr(self, "on_" + endpoint)(request, **values)
        except HTTPException as e:
            return e

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        response = self.dispatch_request(request)
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

    def on_root(self, request):
        """Called when the / page is opened"""
        return Response(self.form, content_type="text/html")

    def on_message(self, request):
        """Called when /message is opened"""
        if request.method == "GET":
            return MethodNotAllowed()

        # we only allow POST requests, we'll check if both
        # parameters we need are present, and if so, invoke the
        # actual messaging function
        if request.method == "POST":
            if "chat_id" not in request.form:
                return BadRequest("Must specify chat_id")
            if "message" not in request.form:
                return BadRequest("Must specify text")

            # if we got this far, it means we're ok
            self.messageFun(request.form["chat_id"], request.form["message"])
            return Response("Message sent")


def run_background(app, interface="127.0.0.1", port=5000):
    """Run the WSGI app in a separate thread, to make integration into
    other programs (that take over the main loop) easier"""
    from werkzeug.serving import run_simple

    t = Thread(target=run_simple, args=(interface, port, app), name="rest")
    t.daemon = True  # so that it dies when the main thread dies
    t.start()
    return t


def dummy_message(chat_id, text):
    """Sample of a function that will be invoked by the REST API
    when a message is received via POST. Normally, this would call
    a function that uses Telegram to send a message to a real user"""
    log.info("You want to send %s to chat=%s", text, chat_id)


if __name__ == "__main__":
    from werkzeug.serving import run_simple

    interface = "127.0.0.1"
    port = 5000
    application = BotRestApi(dummy_message)

    run_simple(interface, port, application, use_debugger=True, use_reloader=True)
