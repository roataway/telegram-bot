import logging
import paho.mqtt.client as paho

log = logging.getLogger("mqtt")


class MqttClient:
    def __init__(
        self,
        name,
        broker="localhost",
        port=1883,
        username=None,
        password=None,
        will=None,
        will_topic=None,
    ):
        """Create an MQTT client instance, with the optional possibility to set a
        last will.

        :param name:        client identifier
        :param broker:      address or name of MQTT server
        :param port:        broker port
        :param username:    str, optional, user
        :param password:    str, optional, password
        :param will:        the last will of the client
        :param will_topic:  the topic to post the last will to"""
        self.client = paho.Client(name, False)
        self.client.on_message = self.on_request
        self.external_handler = None

        if will and will_topic:
            self.client.will_set(will_topic, will, 1, True)

        if username and password:
            self.client.username_pw_set(username, password)
        log.debug("Connecting to broker %s:%s", broker, port)
        self.client.connect(broker, port=port)

    def set_external_handler(self, handler):
        self.external_handler = handler

    def on_request(self, client, userdata, msg):
        """Invoked when a message is received on t_requests"""
        if self.external_handler:
            self.external_handler(client, userdata, msg)
        else:
            log.debug("MQTT IN %s %s", msg.topic, msg.payload)
