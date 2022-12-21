import requests
import json


class CPUtils():
    def __init__(self, host, port, username, password) -> None:
        self.host = f'https://{host}:{port}/api/'
        self.username = username
        self.password = password
        

        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"Accept": "application/json"})
        self.session.verify = False

        self.device_stat = None


    def get_modem_uptime(self):
        if self.device_stat is None:
            self.update_devices()
        
        modem_uptimes = {}
        for device, info in self.device_stat['data'].items():
            if device[0:3] == 'mdm':
                modem_uptimes[device] = info['status']['uptime']

        return modem_uptimes

    def reset_modem(self, mdm):
        endpoint = f'control/wan/devices/{mdm}/reset'

        return self.session.put(self.host+endpoint, data={'data':'true'})

    def get_eth_uptime(self):
        if self.device_stat is None:
            self.update_devices()
        
        return self.device_stat['data']['ethernet-wan']['status']['uptime']


    def update_devices(self):
        endpoint = f'status/wan/devices/'

        resp = self.session.get(self.host + endpoint)
        self.device_stat = json.loads(resp.text)

if __name__ == "__main__":
    username = ''
    password = ''
    with open('secrets.json', 'r') as f:
        j = json.load(f)
        username = j['username']
        password = j['password']

    host = '10.11.12.253'
    port = 8443
    dev = CPUtils(host, port, username, password)
    devices = dev.update_devices()
    print(devices)
    print(dev.get_modem_uptime())
    print(dev.get_eth_uptime())