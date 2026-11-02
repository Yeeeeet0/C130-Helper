import socket
import sys
import threading
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import cdu_helper as cdu


class PreparationTests(unittest.TestCase):
    def test_coordinate_carry_hemispheres_and_bounds(self):
        self.assertEqual(cdu.coordinate(12.999999, True), 'N1300.00')
        self.assertEqual(cdu.coordinate(-179.999999, False), 'W18000.00')
        self.assertEqual(cdu.coordinate(0, False), 'E00000.00')
        for bad in ('', 'nan', 'inf', 91):
            with self.assertRaises(ValueError):
                cdu.coordinate(bad, True)

    def test_waypoint_steps_and_blank_elevation(self):
        rows = cdu.waypoint_rows('ident,lat,lon,elevation_ft\nTEST,42.5,-3.25,\nNEXT,-1,0,100')
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[1]['value'], 'N4230.00W00315.00')
        self.assertEqual(rows[2]['key'], '')
        self.assertEqual(rows[5]['key'], 'L3')

    def test_bad_csv_and_unsupported_characters(self):
        for text in ['ident,lat,lon\nBAD,,12', 'ident,lat,lon\nX,1,181', 'ident,lat,lon', 'name,lat,lon\nX,1,2']:
            with self.assertRaises(ValueError):
                cdu.waypoint_rows(text)
        for text, lsk in [('A\nB', ''), ('A', 'R7'), ('', '')]:
            with self.assertRaises(ValueError):
                cdu.key_sequence(text, lsk)

    def test_ipra_reference_not_coordinate_and_page_two(self):
        rows = cdu.ipra_rows({'rpi': 'RW07', 'elevation': '0', 'map': '3'})
        self.assertEqual(rows[0]['value'], 'RW07')
        self.assertEqual(rows[1]['value'], '0')
        self.assertEqual(rows[2]['page'], 'IPRA 2/2')
        self.assertEqual(cdu.key_sequence('N1.2', 'R6')[-1], 'SELECT_12')

    def test_readiness_and_seat_guard(self):
        api = cdu.CduApi()
        self.assertIn('error', api.send_field('TEST', '', 'pilot', False))
        self.assertIn('error', api.send_field('TEST', '', 'invalid', True))
        self.assertFalse(api.status()['running'])

    def test_acknowledged_transport_and_stop(self):
        received = []
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
            server.bind(('127.0.0.1', 0))
            previous = cdu.ADDRESS
            cdu.ADDRESS = server.getsockname()
            server.settimeout(3)
            api = cdu.CduApi()
            def respond():
                for _ in range(2):
                    data, addr = server.recvfrom(512)
                    request, command = data.decode().split('|', 1)
                    received.append(command)
                    if command.startswith('KEY'):
                        api.stop()
                    server.sendto((request + '|OK').encode(), addr)
            thread = threading.Thread(target=respond)
            thread.start()
            try:
                api.send_field('ABC', 'L1', 'pilot', True)
                deadline = time.monotonic() + 4
                while api.status()['running'] and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertFalse(api.status()['running'])
                self.assertEqual(received, ['PING', 'KEY|pilot|KBD_A'])
                self.assertEqual(api.status()['sent'], 1)
                self.assertIn('Stopped', api.status()['message'])
            finally:
                thread.join(4)
                cdu.ADDRESS = previous


if __name__ == '__main__':
    unittest.main()
