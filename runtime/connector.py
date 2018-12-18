# -*- coding: utf-8 -*-
"""
    Connector manager handles mqtt connections and
    restarts mqtt service when connections are failing
    :copyright: © 2018 by Nuno Gonçalves
    :license: MIT, see LICENSE for more details.
"""

from os import getpid
from signal import signal, SIGTERM, SIGINT
from time import sleep, strftime
from core import Logger, load_config, exec_command, CONNECTOR_LAST_MQTT_RESTART, TIME_FORMAT, CONNECTOR_STATUS, \
    STATUS_RUNNING, STATUS_NOT_RUNNING, CONNECTOR_CONNECTION_OK, CONNECTOR_CONNECTION_STATUS, \
    CONNECTOR_CONNECTION_NOK, CONNECTOR_MQTT_RESTARTS, CONNECTOR_FAILED_CONNECTIONS, CONNECTOR_MQTT_RESTARTS_NAME, \
    CONNECTOR_MQTT_RESTARTS_ICON, CONNECTOR_CONNECTION_STATUS_NAME, CONNECTOR_CONNECTION_STATUS_ICON, \
    CONNECTOR_FAILED_CONNECTIONS_NAME, CONNECTOR_FAILED_CONNECTIONS_ICON, CONNECTOR_STATUS_NAME, \
    CONNECTOR_STATUS_ICON, CONNECTOR_LAST_MQTT_RESTART_NAME, CONNECTOR_LAST_MQTT_RESTART_ICON
from kio import MqttClient, Storage

running = False


class Connector(object):
    """
    Connector logic to restart connections
    """

    def __init__(self, config, storage):
        """
        initializes connector
        :param config: keeper configuration dict
        :param storage: storage access
        """

        self.attempts = 0
        self.command = config["mqtt.restart.command"].split(" ")
        self.mqtt_client = None
        self.registered = False
        put = storage.put
        get_int = storage.get_int
        self.mqtt_restarts = put(CONNECTOR_MQTT_RESTARTS, get_int(CONNECTOR_MQTT_RESTARTS))
        self.failed_connections = put(CONNECTOR_FAILED_CONNECTIONS, get_int(CONNECTOR_FAILED_CONNECTIONS))
        self.states_queue = []
        self.put = put
        self.get = storage.get
        self.inc = storage.inc
        self.logger = Logger()

    def __enter__(self):
        """
        informs when entering context
        :return: Connector object
        """

        self.logger.info("starting connector manager[pid=%s]" % getpid())

        return self

    # noinspection PyShadowingBuiltins
    def __exit__(self, type, value, traceback):
        """
        publishes manager status when exiting context
        :param type:
        :param value:
        :param traceback:
        """

        self.logger.info("stopping connector[pid=%s]" % getpid())
        try:
            self.mqtt_client.publish_state(CONNECTOR_STATUS, STATUS_NOT_RUNNING)
        except:
            pass

    def set_mqtt(self, mqtt_client):
        """
        sets mqtt client
        :param mqtt_client: mqtt client
        """

        self.mqtt_client = mqtt_client

    # noinspection PyUnusedLocal
    def on_connect(self, client, userdata, flags, rc):
        """
        updates connection status on connect
        registers sensors and sends metrics
        :param client: mqtt client
        :param userdata: userdata dict
        :param flags: flags
        :param rc: rc code
        """

        # first time we are connected we register metrics and
        # send initial values
        if not self.registered:
            try:
                publish_state = self.mqtt_client.publish_state
                register = self.mqtt_client.register
                # register all metrics
                register(CONNECTOR_STATUS, CONNECTOR_STATUS_NAME, CONNECTOR_STATUS_ICON)
                register(CONNECTOR_CONNECTION_STATUS, CONNECTOR_CONNECTION_STATUS_NAME,
                         CONNECTOR_CONNECTION_STATUS_ICON)
                register(CONNECTOR_MQTT_RESTARTS, CONNECTOR_MQTT_RESTARTS_NAME, CONNECTOR_MQTT_RESTARTS_ICON)
                register(CONNECTOR_FAILED_CONNECTIONS, CONNECTOR_FAILED_CONNECTIONS_NAME,
                         CONNECTOR_FAILED_CONNECTIONS_ICON)
                register(CONNECTOR_LAST_MQTT_RESTART, CONNECTOR_LAST_MQTT_RESTART_NAME,
                         CONNECTOR_LAST_MQTT_RESTART_ICON)
                # sends initial values
                publish_state(CONNECTOR_STATUS, STATUS_RUNNING)
                publish_state(CONNECTOR_CONNECTION_STATUS, CONNECTOR_CONNECTION_OK)
                publish_state(CONNECTOR_MQTT_RESTARTS, self.mqtt_restarts)
                publish_state(CONNECTOR_FAILED_CONNECTIONS, self.failed_connections)
                publish_state(CONNECTOR_LAST_MQTT_RESTART, self.get(CONNECTOR_LAST_MQTT_RESTART))
                self.registered = True
            except:
                pass

    # noinspection PyUnusedLocal
    def on_disconnect(self, client, userdata, rc):
        """
        updates connection status on disconnect
        :param client: mqtt client
        :param userdata: userdata dict
        :param rc: rc code
        """
        try:
            self.mqtt_client.publish_state(CONNECTOR_CONNECTION_STATUS, CONNECTOR_CONNECTION_NOK)
        except:
            pass

    def on_not_connect(self):
        """
        behavior on connect to mqtt
        after 3 failed attempts we try to restart mqtt and wait it
        to connect again (max 180 seconds)
        """

        if self.attempts >= 3:
            self.logger.warning("max of 3 connection attempts was reached")
            self.logger.warning("restarting mqtt service")
            if exec_command(self.command):
                append = self.states_queue.append
                self.mqtt_restarts = self.inc(CONNECTOR_MQTT_RESTARTS, self.mqtt_restarts)
                append((CONNECTOR_MQTT_RESTARTS, self.mqtt_restarts))
                append((CONNECTOR_LAST_MQTT_RESTART, self.put(CONNECTOR_LAST_MQTT_RESTART, strftime(TIME_FORMAT))))
                self.mqtt_client.wait_connection(60)
                self.attempts = 0
        else:
            self.attempts += 1
            self.failed_connections = self.inc(CONNECTOR_FAILED_CONNECTIONS, self.failed_connections)
            self.logger.warning("broker is not responding (%s of 3)" % self.attempts)
            sleep(10)

    def loop(self):
        """
        sleeps 1 second until next validation
        sends metrics if any to send
        """

        publish_state = self.mqtt_client.publish_state
        try:
            for states in self.states_queue:
                publish_state(states[0], states[1])

            self.states_queue = []
        except:
            pass

        sleep(1)


def start():
    """
    starts this manager and calls it's routine
    loop which monitors mqtt connections
    """

    config = load_config()
    with Storage() as storage, Connector(config, storage) as connector, \
            MqttClient("keeperconnector", config, manager=connector) as mqtt_client:
        del config
        try:
            loop(connector, mqtt_client)
        except Exception as e:
            if running:
                raise e


def loop(connector, mqtt_client):
    """
    continuously check mqtt connections
    :param connector: connector manager
    :param mqtt_client: mqtt client
    """

    global running
    running = True
    while running:
        # if we have been disconnected or failed o connect somehow
        # lets try to reconnect mqtt
        if mqtt_client.connection_status() != 2 and running:
            mqtt_client.reconnect()
            continue

        connector.loop()


# noinspection PyUnusedLocal
def handle_signal(signum=None, frame=None):
    """
    interrupts main loop
    :param signum:
    :param frame:
    """

    global running
    running = False


def main():
    """
    main method which starts the manager
    """

    signal(SIGTERM, handle_signal)
    signal(SIGINT, handle_signal)
    try:
        start()
    except KeyboardInterrupt:
        pass
