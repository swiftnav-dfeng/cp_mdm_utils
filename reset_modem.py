from cp_mdm_utils import CPUtils
import json
import time
import datetime
import sys
import logging
from threading import Thread
import csv
import queue

#logging.basicConfig(filename='output.log', level=logging.DEBUG)
log = logging.getLogger()
log.setLevel(logging.DEBUG)
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s [%(threadName)s] ")
handler = logging.FileHandler('output.log')
handler.setFormatter(log_formatter)
log.addHandler(handler)


class MdmResetThread(Thread):
    def __init__(self, host, port, username, password, name):
        super(MdmResetThread, self).__init__()

        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.name = name

        self.result = None

    def run(self):
        self.result = self.task()
        
    def task(self):
        try:
            self.reset_routine()
        except RuntimeError as e:
            log.warning(f'Exiting: {e}')
            return 1
        except TimeoutError as e:
            log.warning(f'Exiting: {e}')
            return 2
        except Exception as e:
            log.error(f'Exiting: {e}')
            return 3

        log.info("Reset success")
        return 0
        

    def reset_routine(self):
        router = CPUtils(self.host, self.port, self.username, self.password)
        router.update_devices()

        eth_uptime = router.get_eth_uptime()
        if eth_uptime != None:
            log.info(f'ethernet is up, proceed to reset modems')
        else:
            raise RuntimeError('Ethernet is down (no uptime)')

        active_modem = None
        for modem, uptime in router.get_modem_uptime().items():
            if uptime != None:
                active_modem = modem
                log.info(f'active modem {active_modem} uptime {uptime}')
                break

        if active_modem != None:
            result = router.reset_modem(active_modem)
            log.info(f'resetting {active_modem}')
            if json.loads(result.text)['success'] is False:
                raise RuntimeError(f'Modem reset failed {result.text}')

        time.sleep(150)
        end = datetime.datetime.now() + datetime.timedelta(minutes=10)
        while datetime.datetime.now() < end:
            router.update_devices()
            up = router.get_modem_uptime()[active_modem]
            if up is not None:
                log.info(f"successful {active_modem} reset uptime {up}")
                return
            time.sleep(10)

        raise TimeoutError('Timeout waiting for modem reset')


def get_stations(file):
    stations = {}
    with open(file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Status'] == 'Installed':
                print(row)
                stations[row['NetCloud Custom Name']] = row['IP Address']

    return stations

if __name__ == "__main__":
    port = 8443
    username = ''
    password = ''
    with open('secrets.json', 'r') as f:
        j = json.load(f)
        username = j['username']
        password = j['password']

    file = 'tracker.csv'
    stations = get_stations(file)

    threads = []
    num_stations = 0
    for station, host in stations.items():
        threads.append(MdmResetThread(host, port, username, password, name=f'thread-{station}'))
        num_stations += 1

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    results = {}
    for thread in threads:
        results[thread.name] = thread.result

    logging.info("finished")
    logging.info(f'num_stations {num_stations}, num_results {len(results)}')
    logging.info(results)
