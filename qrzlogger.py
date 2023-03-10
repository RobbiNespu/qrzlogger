#!/usr/bin/env python3

# pylint: disable=W1401

"""
+---------------------------------------------------------------------+
|                            _                                        |
|                __ _ _ _ __| |___  __ _ __ _ ___ _ _                 |
|               / _` | '_|_ / / _ \/ _` / _` / -_) '_|                |
|               \__, |_| /__|_\___/\__, \__, \___|_|                  |
|                  |_|             |___/|___/                         |
|                                                                     |
|                                                                     |
| A python application to log QSOs directly to QRZ.com from the CLI   |
|                                                                     |
| Author:           Michael Clemens, DK1MI (qrzlogger@qrz.is)         |
|                                                                     |
| Documentation:    Please see the README.md file                     |
| License:          Please see the LICENSE file                       |
| Repository:       https://github.com/exitnode/qrzlogger             |
|                                                                     |
+---------------------------------------------------------------------+
"""

import urllib
import re
import datetime
import os
from os.path import exists
import sys
import csv
import configparser
import zipfile
import signal
import atexit
from datetime import timezone
from colored import attr, fg
from requests.structures import CaseInsensitiveDict
from prettytable import PrettyTable
import xmltodict
import requests
from pathlib import Path


class QRZLogger():
    """QRZLogger class"""

    def __init__(self):
        """initialize things"""

        self.version = "0.9.0"



        self.config = configparser.ConfigParser()
        self.home_dir = str(Path.home())
        self.config_dir = self.home_dir + "/.config/qrzlogger/"
        # Check if config directory exists and else create it
        Path(self.config_dir).mkdir(parents=True, exist_ok=True)
        self.config_file = os.path.expanduser(self.config_dir + 'qrzlogger.ini')
        self.read_config(self.config, self.config_file)

        self.check_files()

        if self.config['lotw']['user'] != "N0CALL" and self.check_lotw_confirmed:
            self.confirmed_entities = self.get_confirmed_entities()

        if self.check_cty:
            with open(self.config_dir + self.config['files']['cty'], encoding='us-ascii') as csvfile:
                self.cty = list(csv.reader(csvfile, delimiter=','))

        if self.check_lotw_activity:
            with open(self.config_dir + self.config['files']['lotw_activity'], encoding='us-ascii') as csvfile:
                self.lotw_activity = list(csv.reader(csvfile, delimiter=','))



        if self.config and self.config['log']['log_file']:
            self.log_file = self.config['log']['log_file']
        else:
            self.log_file = os.path.expanduser('~/.qrzlogger.log')

        self.contest = False
        if len(sys.argv) > 1 and str(sys.argv[1]) == "-c":
            self.contest = True

        # QRZ.com URLs
        self.xml_url = "https://xmldata.QRZ.com/xml/current/"
        self.api_url = "https://logbook.qrz.com/api"

        # headers for all POST requests
        self.headers = CaseInsensitiveDict()
        self.headers["Content-Type"] = "application/x-www-form-urlencoded"

        # Default colors
        self.inputcol = attr('reset')
        self.hlcol = attr('reset')
        self.defvalcol = attr('reset')
        self.errorcol = attr('reset')
        self.successcol = attr('reset')
        self.tablecol = attr('reset')
        self.logocol = attr('reset')

        self.qso = None
        self.recent_qso_limit = 5
        self.recent_qsos = []

        # read colors from config and overwrite default vaulues
        self.config_colors()

    def print_banner(self):
        """print an awesome banner"""
        ver = self.version
        # print the banner
        print(self.logocol)
        print("              _                        ")
        print("  __ _ _ _ __| |___  __ _ __ _ ___ _ _ ")
        print(" / _` | '_|_ / / _ \/ _` / _` / -_) '_|")
        print(" \__, |_| /__|_\___/\__, \__, \___|_|  ")
        print("    |_|  -=DK1MI=-  |___/|___/ v"+ver+"  ")
        print(attr('reset'))


    def config_colors(self):
        """Read color settings from config file"""
        if self.config and self.config['colors']['use_colors'] == "yes":
            self.inputcol = fg(self.config['colors']['inputcol'])
            self.hlcol = fg(self.config['colors']['hlcol'])
            self.defvalcol = fg(self.config['colors']['defvalcol'])
            self.errorcol = fg(self.config['colors']['errorcol'])
            self.successcol = fg(self.config['colors']['successcol'])
            self.tablecol = fg(self.config['colors']['tablecol'])
            self.logocol = fg(self.config['colors']['logocol'])


    @staticmethod
    def read_config(config, file_name):
        """reads the configuration from the config file or
        creates a default config file if none could be found"""
        if os.path.isfile(file_name):
            config.read(file_name)
        else:
            config = configparser.ConfigParser()
            config['qrz.com'] = {
                'station_call': 'MYCALL',
                'api_key': '1234-ABCD-1234-A1B2',
                'qrz_user': 'MYCALL',
                'qrz_pass': 'my_secret_password',
                'xml_fields': '("call", "band", "mode", "qso_date", "time_on", "rst_sent", "rst_rcvd", "comment")'}
            config['files'] = {
                'cty': 'cty.csv',
                'cty_url': 'https://www.country-files.com/bigcty/download/bigcty.zip',
                'lotw_confirmed': 'lotw.adi',
                'lotw_activity': 'lotw-user-activity.csv',
                'lotw_activity_url': 'https://lotw.arrl.org/lotw-user-activity.csv'}
            config['lotw'] = {
                'user': 'N0CALL',
                'password': 'CHANGEME',
                'mode': 'ssb'}
            config['log'] = {
                'log_file': '/tmp/qrzlogger.log'}
            config['qso_defaults'] = {
                'band': '20m',
                'mode': 'SSB',
                'rst_rcvd': '59',
                'rst_sent': '59',
                'tx_pwr': '100'}
            config['colors'] = {
                'use_colors': 'yes',
                'inputcol': 'yellow',
                'hlcol': 'yellow',
                'defvalcol': 'light_blue',
                'errorcol': 'red',
                'successcol': 'green',
                'tablecol': 'light_blue',
                'logocol': 'yellow'}
            config['bandfreqs'] = {
                '160m': '1.850',
                '80m': '3.700',
                '60m': '5.355',
                '40m': '7.100',
                '30m': '10.130',
                '20m': '14.200',
                '17m': '18.130',
                '15m': '21.200',
                '12m': '24.950',
                '10m': '28.500',
                '6m': '50.150',
                '2m': '145.500',
                '70cm': '432.300' }

            with open(file_name, 'w') as configfile:
                config.write(configfile)
            print("\nNo configuration file found. A new configuration file has been created.")
            print("\nPlease edit the file " + file_name + " and restart the application.\n" )
            sys.exit()
        return config


    @staticmethod
    def remove_indicators(call):
        """returns the actual call sign without any indicators
        (e.g, "/p" or "F/")"""

        # set the return value to the value of "call"
        cleaned_call = call
        # check if the callsign has a suffix (.e.g. /p)
        if call.endswith(("/P","/MM","/M","/QRP")):
            cleaned_call = call.rsplit('/', 1)[0]
        # check if the callsign has a prefix (e.g. DL/)
        if "/" in cleaned_call:
            cleaned_call = re.sub(r'^\w+/', "", cleaned_call)
        return cleaned_call


    def print_table(self, tab):
        """Print the table object to stdout"""
        print(self.tablecol)
        print(tab)
        print(attr('reset'))

    @staticmethod
    def download_file(url, local_filename):
        """downloads a file via HTTP and saves it to a defined file"""
        with requests.get(url, stream=True) as request:
            request.raise_for_status()
            with open(local_filename, 'wb') as file:
                for chunk in request.iter_content(chunk_size=8192):
                    file.write(chunk)
        return local_filename


    def check_files(self):
        """Checks if all necessary files are in the file system.
        Downloads all files and unzips them (if necessary)"""

        # check for lotw qsl information file
        if self.config['lotw']['user'] != "N0CALL":
            self.check_lotw_confirmed = exists(self.config_dir + self.config['files']['lotw_confirmed'])
            if not self.check_lotw_confirmed:
                print("The file " + self.config_dir + self.config['files']['lotw_confirmed'] + " is missing.")
                user = self.config['lotw']['user']
                password = self.config['lotw']['password']
                mode = self.config['lotw']['mode']
                url = "https://lotw.arrl.org/lotwuser/lotwreport.adi?login={}&password={}"\
                    "&qso_query=1&qso_qsl=yes&qso_mode={}&qso_qsldetail=yes&"\
                    "qso_qslsince=1970-01-01".format(user, password, mode)
                print("Trying to download " + url)
                self.download_file(url, self.config_dir + self.config['files']['lotw_confirmed'])
                self.check_lotw_confirmed = exists(self.config_dir + self.config['files']['lotw_confirmed'])
                if self.check_lotw_confirmed:
                    print("File successfully downloaded")
                else:
                    print("something went wrong while downloading " + url)
        else:
            self.check_lotw_confirmed = False

        # check for cty.csv file
        self.check_cty = exists(self.config_dir + self.config['files']['cty'])
        if not self.check_cty:
            url = self.config['files']['cty_url']
            print("The file " + self.config_dir + self.config['files']['cty'] + " is missing.")
            print("Trying to download " + url)
            # TODO: pfad?
            zip_name = self.download_file(url, self.config_dir + "bigcty.zip" )
            with zipfile.ZipFile(zip_name, 'r') as zip_ref:
                zip_ref.extract("cty.csv", path=self.config_dir)
            os.remove(zip_name)
            self.check_cty = exists(self.config_dir + self.config['files']['cty'])
            if self.check_cty:
                print("File successfully downloaded and extracted.")
            else:
                print("something went wrong while downloading " + url)

        # check for lotw user activity file
        self.check_lotw_activity = exists(self.config_dir + self.config['files']['lotw_activity'])
        if not self.check_lotw_activity:
            url = self.config['files']['lotw_activity_url']
            print("The file " + self.config_dir + self.config['files']['lotw_activity'] + " is missing.")
            print("Trying to download " + url)
            self.download_file(url, self.config_dir + self.config['files']['lotw_activity'])
            self.check_lotw_activity = exists(self.config_dir + self.config['files']['lotw_activity'])
            if self.check_lotw_activity:
                print("File successfully downloaded")
            else:
                print("something went wrong while downloading " + url)


    def get_confirmed_entities(self):
        """Reads the file downlaoded from LotW with all confirmed QSOs,
        extracts all confirmed DXCCs and puts them into a list"""
        ret = []
        with open(self.config_dir + self.config['files']['lotw_confirmed'], encoding='us-ascii') as file:
            for row in file:
                if re.search("<DXCC:", row):
                    dxcc = row.partition(">")[2].lower().rstrip()
                    if dxcc not in ret:
                        ret.append(dxcc)
        return ret


    def check_lotw(self, call):
        """Reads the LotW user activity file and returns the date
        of the last upload date if a specific call sign"""
        ret = ""
        for row in self.lotw_activity:
            if call == row[0]:
                ret = row[1]
                return ret
        return ret


    def get_cty_row(self, call):
        """Parses all CTY records, tries to find the DXCC entity of a
        specific call sign and returns the line as a list of strings"""
        done = False
        while not done:
            for row in self.cty:
                entities = row[9].replace(";", "").replace("=", "").split(" ")
                # TODO: Check if it is a speciall call (=) and mark it in the list
                for prefix in entities:
                    if call == prefix:
                        return row
            call = call[:-1]
            if call == "":
                return ["-", "-", "-", "-", "-", "-", "-"]
        return None


    #####################################################
    #             QRZ.com API Functions                 #
    #####################################################

    def get_session(self):
        """Generate a session for QRZ.com's xml service with
        the help of the QRZ.com username and password"""
        session_key = None
        data = {
            'username' : self.config['qrz.com']['qrz_user'],
            'password' : self.config['qrz.com']['qrz_pass']
            }

        try:
            session = requests.Session()
            session.verify = True
            result = session.post(self.xml_url, data=data)
            if result.status_code == 200:
                raw_session = xmltodict.parse(result.content)
                if raw_session.get('QRZDatabase').get('Session').get('Error'):
                    print(self.errorcol + "\nError while logging into the QRZ.com XML Service:\n")
                    print(raw_session.get('QRZDatabase').get('Session').get('Error'))
                    print(attr('reset'))
                session_key = raw_session.get('QRZDatabase').get('Session').get('Key')
                if session_key:
                    return session_key
        except requests.exceptions.ConnectionError as e_conn:
            print(self.errorcol + "\nUnable to connect to xmldata.qrz.com:")
            print(e_conn)
            print("\nPlease check if\n * username and password are correct \
                    (see config.ini)\n * you are connected to the internet")
            print(attr('reset'))
        except: # pylint: disable=bare-except
            print(self.errorcol + "\nsomething unexpected has happened:\n")
            print(attr('reset'))
        return session_key


    def send_request(self, post_data):
        """Sends a POST request to QRZ.com, checks for errors
        and returns the response"""
        try:
            resp = requests.post(self.api_url, headers=self.headers, data=post_data)
            if resp.status_code == 200:
                str_resp = resp.content.decode("utf-8")
                response = urllib.parse.unquote(str_resp)
                resp_list = response.splitlines()
                if resp_list[0]:
                    if "invalid api key" in resp_list[0]:
                        print(self.errorcol + "\nThe API key configured \
                                in config.ini is not correct.\n" + attr('reset'))
                    else:
                        return response
            elif resp.status_code == 404:
                print(self.errorcol + "\nThe API URL could not be found. \
                        Please check the URL in config.ini\n" + attr('reset'))
        except requests.exceptions.ConnectionError as e_conn:
            print(self.errorcol + "\nUnable to connect to xmldata.qrz.com:")
            print(e_conn)
            print("\nPlease check if you are connected to the internet")
            print(attr('reset'))
        except: # pylint: disable=bare-except
            print(self.errorcol + "\nsomething unexpected has happened:\n")
            print(e_conn)
            print(attr('reset'))
        return None


    def get_call_data(self, call, session_key):
        """Query QRZ.com's xml api to gather information
        about a specific call sign"""

        data = {
            's' : session_key,
            'callsign' : call
            }

        try:
            session = requests.Session()
            session.verify = True
            result = session.post(self.xml_url, data=data)
            raw = xmltodict.parse(result.content).get('QRZDatabase')
            calldata = raw.get('Callsign')
            if calldata:
                return calldata
        except requests.exceptions.ConnectionError as e_conn:
            print(self.errorcol + "\nUnable to connect to xmldata.qrz.com:")
            print(e_conn)
            print("\nPlease check if you are connected to the internet")
            print(attr('reset'))
        except: # pylint: disable=bare-except
            print(self.errorcol + "\nsomething unexpected has happened:\n")
            print(attr('reset'))
        return None


    def get_qsos(self, option):
        """Query QRZ.com's logbook for all previous QSOs
        with a specific call sign or for a specific logid"""

        result = [{}]
        post_data = {
            'KEY' : self.config['qrz.com']['api_key'],
            'ACTION' : 'FETCH',
            'OPTION' : "TYPE:ADIF," + option
            }
        post_data = urllib.parse.urlencode(post_data)

        response = self.send_request(post_data)

        if response:
            resp_list = response.splitlines()
            for resp in resp_list:
                if not resp:
                    result.append({})
                else:
                    if any(s+":" in resp for s in self.config['qrz.com']['xml_fields']):
                        resp = re.sub('&lt;','',resp, flags=re.DOTALL)
                        resp = re.sub(':.*&gt;',":",resp, flags=re.DOTALL)
                        value = re.sub('^.*:',"",resp, flags=re.DOTALL)
                        key = re.sub(':.*$',"",resp, flags=re.DOTALL)
                        result[-1][key] = value
        return result


    def send_qso(self, qso, call):
        """Sends the previously collected QSO information as a new
        QRZ.com logbook entry via the API"""

        logid = "null"
        log_status = "FAILED:  "

        # construct ADIF QSO entry
        adif = '<station_callsign:' + str(len(self.config['qrz.com']['station_call'])) \
                + '>' + self.config['qrz.com']['station_call']
        adif += '<call:' + str(len(call)) + '>' + call
        for field in qso:
            adif += '<' + field + ':' + str(len(qso[field][1])) + '>' + qso[field][1]
        adif += '<eor>'

        # construct POST data
        post_data = { 'KEY' : self.config['qrz.com']['api_key'], \
                'ACTION' : 'INSERT', 'ADIF' : adif }

        # URL encode the payload
        data = urllib.parse.urlencode(post_data)
        # send the POST request to QRZ.com
        response = self.send_request(data)

        # Check if the upload failed and print out
        # the reason plus some additional info
        if response:
            if "STATUS=FAIL" in response:
                print(self.errorcol)
                print("QSO upload failed. QRZ.com has send the following reason:\n")
                resp_list = response.split("&")
                for item in resp_list:
                    print(item)
                print("\nPlease review the following request that led to this error:\n")
                print(attr('reset'))
                print(post_data)
            else:
                try:
                    logid = re.search('LOGID=(\d+)', response).group(1)
                    print(self.successcol)
                    print("QSO successfully uploaded to QRZ.com (LOGID "+ logid + ")")
                    log_status = "SUCCESS: "
                    print(attr('reset'))
                except: # pylint: disable=bare-except
                    logid = "null"
                    print(self.errorcol)
                    print("\nQSO upload to QRZ.com failed!\n")
                print(attr('reset'))
            with open(self.log_file, "a") as log:
                log.write(log_status + adif + "\n")
        return logid



    #####################################################
    #     Functions for generating  ASCII Tables        #
    #####################################################

    @staticmethod
    def get_qso_table(result):
        """Generate a pretty ascii table containing all
        previous QSOs with a specific call sign"""

        table = PrettyTable(['Date', 'Time', 'Band', 'Mode', 'RST-S', 'RST-R', 'Power', 'QRZ', 'LotW', 'Comment'])
        for qso in result:
            if "qso_date" in qso:
                date = datetime.datetime.strptime(qso["qso_date"], '%Y%m%d').strftime('%Y/%m/%d')
                time = datetime.datetime.strptime(qso["time_on"], '%H%M').strftime('%H:%M')
                # add missing fields to dict
                for field in ["band", "mode", "rst_sent", "rst_rcvd", "tx_pwr", "app_qrzlog_status", "lotw_qsl_rcvd", "comment"]:
                    if field not in qso:
                        qso[field] = ""
                table.add_row([date, time, qso["band"], qso["mode"], qso["rst_sent"], \
                        qso["rst_rcvd"], qso["tx_pwr"], qso["app_qrzlog_status"], qso["lotw_qsl_rcvd"], qso["comment"]])
        table.align = "r"
        return table


    @staticmethod
    def get_xml_query_table(result):
        """Print a pretty ascii table containing all interesting
        data found for a specific call sign"""

        table = PrettyTable(['key', 'value'])
        if "fname" in result:
            table.add_row(["First Name", result["fname"]])
        if "name" in result:
            table.add_row(["Last Name", result["name"]])
        if "addr1" in result:
            table.add_row(["Street", result["addr1"]])
        if "addr2" in result:
            table.add_row(["City", result["addr2"]])
        if "state" in result:
            table.add_row(["State", result["state"]])
        if "country" in result:
            table.add_row(["Country", result["country"]])
        if "grid" in result:
            table.add_row(["Locator", result["grid"]])
        if "email" in result:
            table.add_row(["Email", result["email"]])
        if "qslmgr" in result:
            table.add_row(["QSL via:", result["qslmgr"]])
        table.align = "l"
        table.header = False
        return table


    @staticmethod
    def get_extra_info_table(extra_info):
        """Print a pretty ascii table containing some
        extra info"""

        table = PrettyTable(['key', 'value'])
        if "cty_country" in extra_info:
            table.add_row(["Country:", extra_info["cty_country"]])
        if "cty_continent" in extra_info:
            table.add_row(["Continent:", extra_info["cty_continent"]])
        if "lotw_call_date" in extra_info and extra_info["lotw_call_date"] != "":
            table.add_row(["LotW uploaded ({}):".format(extra_info["lotw_call"]), extra_info["lotw_call_date"]])
        if "lotw_cleaned_call_date" in extra_info and extra_info["lotw_cleaned_call_date"] != "":
            table.add_row(["LotW uploaded ({}):".format(extra_info["lotw_cleaned_call"]), extra_info["lotw_cleaned_call_date"]])
        table.align = "l"
        table.header = False
        return table


    @staticmethod
    def get_qso_detail_table(qso):
        """Print a pretty ascii table containing all
        previously entered user data"""

        table = PrettyTable(['key', 'value'])
        for item in qso:
            table.add_row([qso[item][0], qso[item][1]])
        table.align = "l"
        table.header = False
        return table


    @staticmethod
    def get_recent_qso_table(recent_qsos):
        """Print a pretty ascii table containing
        the n previous QSOs"""

        table = PrettyTable(['Time', 'Frequency', 'Call'])
        for hist_qso in recent_qsos:
            table.add_row([hist_qso[1], hist_qso[2], hist_qso[0]])

        table.align = "l"
        table.header = True
        return table


    #####################################################
    #          User Interaction Functions               #
    #####################################################

    def query_qso_data(self, qso):
        """Queries QSO specific data from the user via
        the command line"""

        date_time = datetime.datetime.now(timezone.utc)
        dt_now = date_time.replace(tzinfo=timezone.utc)

        # If this is the first try filling out the QSO fields
        # then we use defaults
        if qso is None:
            if not self.contest:
                questions = {
                    "band": ["Band", self.config['qso_defaults']['band']],
                    "rst_rcvd": ["RST Received", self.config['qso_defaults']['rst_rcvd']],
                    "rst_sent": ["RST Sent", self.config['qso_defaults']['rst_sent']],
                    "comment": ["Comment", ""],
                    "freq": ["Frequency", ""],
                    "mode": ["Mode", self.config['qso_defaults']['mode']],
                    "tx_pwr": ["Power (in W)", self.config['qso_defaults']['tx_pwr']],
                    "qso_date" : ["QSO Date", dt_now.strftime("%Y%m%d")],
                    "time_on": ["QSO Time", dt_now.strftime("%H%M")]
                    }
            else:
                questions = {
                    "band": ["Band", self.config['qso_defaults']['band']],
                    "srx": ["Serial Received", "001"],
                    "srx_string": ["Info Received", ""],
                    "stx": ["Serial Sent", "001"],
                    "stx_string": ["Info Sent", ""],
                    "freq": ["Frequency", ""],
                    "mode": ["Mode", self.config['qso_defaults']['mode']],
                    "rst_rcvd": ["RST Received", self.config['qso_defaults']['rst_rcvd']],
                    "rst_sent": ["RST Sent", self.config['qso_defaults']['rst_sent']],
                    "comment": ["Comment", ""],
                    "qso_date" : ["QSO Date", dt_now.strftime("%Y%m%d")],
                    "time_on": ["QSO Time", dt_now.strftime("%H%M")]
                    }
        # if this is not the first try, we pre-fill the
        # vaulues we got from the last try
        else:
            questions = qso

        # We now loop through all defined fields and ask
        # the user for input
        for question in questions:
            txt = self.inputcol + questions[question][0] + " [" + self.defvalcol \
                    + questions[question][1] + self.inputcol + "]:" + attr('reset')
            inp = input(txt)
            # If the user just hits enter, we keep the default value.
            # If not, we keep the data provided by the user
            if inp == "c":
                return None
            if inp == "d":
                return questions
            if inp == "quit" or inp == "exit":
                sys.exit()
            if inp != "":
                questions[question][1] = inp
            # check if we are asking for the band
            if question == "band":
                # check if the band is in the bandfreqs dictionary
                try:
                    # populate the frequency with a common freq of this band
                    bandfreqs = dict(self.config.items('bandfreqs'))
                    questions['freq'][1] = bandfreqs[questions[question][1]]
                except: # pylint: disable=bare-except
                    print(self.errorcol + "\nUnable to read default frequency \
                            values from config file." + attr('reset'))
        return questions


    def get_input_callsign(self):
        """query a call sign from the user"""
        call = ""
        while True:
            call = input("\n\n%sEnter Callsign:%s " % (self.inputcol, attr('reset')))
            if call == "quit" or call == "exit":
                sys.exit()
            # check if it has the format of a valid call sign
            # (at least 3 characters, only alphanumeric and slashes)
            if not (len(call) > 2 and call.replace("/", "").isalnum()):
                print(self.errorcol + "\nPlease enter a callsign with\n * at least \
                        3 characters\n * only letters, numbers and slashes" + attr('reset'))
                continue
            # make the call sign all upper case
            call = call.upper()
            break
        return call


    def confirm_and_submit_qso(self, call):
        """ask user if everything is ok. If not, start over."""
        done = False
        while True:
            answer = input("\n" + self.inputcol + "Is this correct? [" + \
                    self.defvalcol +  "y/n/c/quit" + self.inputcol + "]: " + attr('reset'))
            answer = answer.upper()
            if answer == "Y":
                while True:
                    logid = self.send_qso(self.qso, call)
                    if logid and logid != "null":
                        break
                    answer = input("\n" + self.inputcol + "QSO Upload failed. Retry? [" + \
                            self.defvalcol +  "y/n" + self.inputcol + "]: " + attr('reset'))
                    answer = answer.upper()
                    if answer == "N":
                        done = True
                        break
                if logid and logid.lower() != "null":
                    # pull the uploaded QSO from QRZ
                    result = self.get_qsos("LOGIDS:"+ logid)
                    if result and result[0]:
                        self.print_table(self.get_qso_table(result))
                        # add some of the QSO detail to the recent_qsos list
                        self.recent_qsos.append([call, self.qso["time_on"][1], self.qso["freq"][1]])
                        if len(self.recent_qsos)>self.recent_qso_limit:
                            self.recent_qsos.pop(0)
                    done = True
                    break
                break
            if answer == "C":
                done = True
                break
            if answer == "N":
                break
            if answer == "QUIT" or answer == "EXIT":
                sys.exit()
        return done



def handler(signum, frame): # pylint: disable=W0613
    """method for handlich SIGINTs"""
    return None


def quit_gracefully():
    """Prints a message when the application is terminated"""
    print("\n73!\n")



#####################################################
#                  Main Routine                     #
#####################################################

def main():
    """the main routine"""

    # signal handling for ctrl+c and ctrl+d
    signal.signal(signal.SIGINT, handler)
    atexit.register(quit_gracefully)

    qrz = QRZLogger()
    qrz.print_banner()

    if qrz.contest:
        print("\nContest mode enabled.")

    keeponlogging = True
    session_key = None


    # Begin the main loop
    while keeponlogging:
        # get a session after logging into QRZ with user/pass
        session_key = qrz.get_session()
        qrz.qso = None
        # print a table containing the last n logged QSOs
        if qrz.recent_qsos:
            print ('\n%s%sYour last %s logged QSOs%s' \
                    % (attr('underlined'), qrz.hlcol, \
                    qrz.recent_qso_limit, attr('reset')))
            qrz.print_table(qrz.get_recent_qso_table(qrz.recent_qsos))
        # query a call sign from the user
        call = qrz.get_input_callsign()
        cleaned_call = qrz.remove_indicators(call)
        # query call sign data from QRZ
        result = qrz.get_call_data(call, session_key)
        # the query was successful
        if result:
            print ('\n%s%sQRZ.com results for %s%s' \
                    % (attr('underlined'), qrz.hlcol, call, attr('reset')))
            # generate a nice ascii table with the result
            qrz.print_table(qrz.get_xml_query_table(result))
        # the query was unsuccessful
        else:
            print ('\n%s%s has no record on QRZ.com ??\_(???)_/??%s' \
                    % (qrz.errorcol, call, attr('reset')))
            if call != cleaned_call:
                # query call sign data from QRZ
                result = qrz.get_call_data(cleaned_call, session_key)
                # the query was successful
                if result:
                    print ('\n%s%sShowing results for %s instead%s' \
                            % (attr('underlined'), qrz.hlcol, cleaned_call, attr('reset')))
                    # generate a nice ascii table with the result
                qrz.print_table(qrz.get_xml_query_table(result))
            print("")


        extra_info = {}

        # If the CTY file is available, further information will be
        # gathered from it, e.g. continent, country
        if qrz.check_cty:
            cty_details = qrz.get_cty_row(call)
        else:
            cty_details = ["-","-","-","-","-","-","-","-","-","-"]

        extra_info["cty_country"] = cty_details[1]
        extra_info["cty_continent"] = cty_details[3]

        # If the LotW user activity file is available and the call
        # sign in question is actually a LotW user, the lsat upload
        # date will be displayed
        if qrz.check_lotw_activity: 
            lotw = qrz.check_lotw(call)
            extra_info["lotw_call"] = call
            extra_info["lotw_call_date"] = lotw
            if call != cleaned_call:
                lotw = qrz.check_lotw(cleaned_call)
                extra_info["lotw_cleaned_call"] = cleaned_call
                extra_info["lotw_cleaned_call_date"] = lotw


        # Print the table with additional infos on the call
        print ('%s%sExtra (non-QRZ.com) info for %s%s' \
                % (attr('underlined'), qrz.hlcol, call, attr('reset')))
        qrz.print_table(qrz.get_extra_info_table(extra_info))

        if cty_details[2] and cty_details[2] not in qrz.confirmed_entities:
            print ('\n%s%s>>> New One! (not confirmed via Lotw) <<<%s\n\n' \
                    % (attr('bold'), qrz.hlcol,  attr('reset')))


        # pull all previous QSOs from tzhe QRZ logbook
        result = qrz.get_qsos("CALL:"+ call)
        # ignore this part if there were no previous QSOs
        if result and result[0]:
            print ('%s%sPrevious QSOs with %s%s' \
                    % (attr('underlined'), qrz.hlcol, call, attr('reset')))
            qrz.print_table(qrz.get_qso_table(result))

        print ('%s%sEnter new QSO details below%s%s (enter \'c\' to cancel, \'d\' to fast forward)%s\n' \
                % (attr('underlined'), qrz.hlcol, attr('reset'), qrz.hlcol, attr('reset'),))

        done = False

        # we now ask the user for QSO details until he/she is happy with the result
        while not done:
            # query QSO details from the user
            qrz.qso = qrz.query_qso_data(qrz.qso)
            # the user has answered all questions
            if qrz.qso:
                print ('\n%s%sPlease review your choices%s' \
                        % (attr('underlined'), qrz.hlcol, attr('reset')))
                qrz.print_table(qrz.get_qso_detail_table(qrz.qso))
                done = qrz.confirm_and_submit_qso(call)
                '''
                # add some of the QSO detail to the recent_qsos list
                recent_qsos.append([call, qrz.qso["time_on"][1], qrz.qso["freq"][1]])
                if len(recent_qsos)>qrz.recent_qso_limit:
                    recent_qsos.pop(0)
                '''
            # the user has entered 'c' during the QSO detail entering process
            else:
                done = True
                qrz.qso = None
                continue


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EOFError:
        pass
