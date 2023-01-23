from cp_mdm_utils import CPUtils
import json
import time
import datetime
import sys
import logging
from threading import Thread
import csv
import queue

NUM_THREADS = 2

#logging.basicConfig(filename='output.log', level=logging.DEBUG)
log = logging.getLogger()
log.setLevel(logging.DEBUG)
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s [%(threadName)s] ")
handler = logging.FileHandler('output.log')
handler.setFormatter(log_formatter)
log.addHandler(handler)

results = {}

class MdmResetThread(Thread):
    def __init__(self, name, q:queue.Queue, result_callback, daemon=True):
        super(MdmResetThread, self).__init__(name=name, daemon=daemon)

        self.q = q

        self.result_callback = result_callback

        self.item = {
            'station':None,
            'host':None,
            'port':None,
            'username':None,
            'password':None
            }

    def run(self):
        while True:
            try:
                self.item = self.q.get(timeout=5)
            except queue.Empty as e:
                log.info(e)
                log.info(f'queue is empty, {self.name} terminating')
                return

            result = self.task()
            self.result( (self.item['station'],result), self.result_callback )
            self.q.task_done()
        
    def task(self):
        try:
            self.reset_routine()
        except RuntimeError as e:
            log.warning(f"{self.item['station']} Exiting: {e}")
            return 1
        except TimeoutError as e:
            log.warning(f"{self.item['station']} Exiting: {e}")
            return 2
        except Exception as e:
            log.error(f"{self.item['station']} Exiting: {e}")
            return 3

        log.info(f"{self.item['station']} Reset success")
        return 0
        

    def reset_routine(self):
        router = CPUtils(self.item['host'], self.item['port'], self.item['username'], self.item['password'])
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

    def result(self, result, callback:callable):
        callback(result)

def result_collector(result):
    results[result[0]] = result[1]


def get_stations(file):
    # file is a csv generate from this Sitetracker tracker:
    # https://sitetracker-swiftnavigation.lightning.force.com/lightning/r/sitetracker__StGridView__c/a0q4P00000T2hTXQAZ/view
    # Filter Product Name to IBR600C (only modem used in EU)


    stations = {}
    with open(file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Product Name'] == 'IBR600C':
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
    max_t = min(NUM_THREADS, len(stations))

    q = queue.Queue()

    for i in range(max_t):
        worker = MdmResetThread(f'thread-{i}', q, result_collector, daemon=True)
        worker.start()
        threads.append(worker)

    for station, host in stations.items():
        item = {
            'station':station,
            'host':host,
            'port':8443,
            'username':username,
            'password':password
        }
        q.put(item)

    q.join()

    for t in threads:
        t.join()


    log.info("finished")
    log.info(f'num_stations {len(stations)}, num_results {len(results)}')
    log.info(results)
