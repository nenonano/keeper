from os import environ, getcwd, mkdir
from os.path import join
environ["KEEPER_HOME"] = join(getcwd(), "mqtt")
from shutil import rmtree, copy
from unittest import TestCase
from core.mqtt import MqttClient

from core import common


class TestMqtt(TestCase):
    def setUp(self):
        mkdir(environ["KEEPER_HOME"])
        config_path = join(environ["KEEPER_HOME"], "config")
        mkdir(config_path)
        copy(join(environ["KEEPER_HOME"], "..", "..", "config", "keeper-config.yaml"), config_path)

    def tearDown(self):
        rmtree(environ["KEEPER_HOME"])

    def test_connected(self):
        config = common.load_config()
        mqtt_client = MqttClient("keepermqtttest", config)
        mqtt_client.reconnect()
        self.assertEqual(mqtt_client.connection_status(), 2)

    def test_not_connected(self):
        config = common.load_config()
        config["mqtt.broker"] = "1.1.1.1"
        mqtt_client = MqttClient("keepermqtttest", config)
        mqtt_client.reconnect(wait=False)
        self.assertEqual(mqtt_client.connection_status(), 0)

    def test_wait(self):
        config = common.load_config()
        mqtt_client = MqttClient("keepermqtttest", config)
        mqtt_client.wait_connection()
        self.assertEqual(mqtt_client.connection_status(), 2)

    def test_is_connected(self):
        config = common.load_config()
        mqtt_client = MqttClient("keepermqtttest", config)
        mqtt_client.wait_connection()
        self.assertEqual(mqtt_client.connection_status(), 2)
        mqtt_client.disconnect()
        self.assertEqual(mqtt_client.connection_status(), 0)