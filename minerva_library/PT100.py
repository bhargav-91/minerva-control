from configobj import ConfigObj
import time, sys, socket, logging, datetime, ipdb, time, json, os, struct
import numpy as np
from scipy.interpolate import interp1d
import threading

class PT100:

    def __init__(self, config=None, base=None):

        self.config_file = config
        self.num = config[-5]
	self.base_directory = base
	self.load_config()
	self.setup_logger()

    def load_config(self):
	
            try:
                    config = ConfigObj(self.base_directory + '/config/' + self.config_file)
            except:
                    print('ERROR accessing configuration file: ' + self.config_file)
                    sys.exit()
            self.ip = config['IP']
            self.port = int(config['PORT'])
            self.logger_name = config['LOGGER_NAME']
            self.description = config['DESCRIPTION']
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
            # reset the night at 10 am local                                                                                                 
            today = datetime.datetime.utcnow()
            if datetime.datetime.now().hour >= 10 and datetime.datetime.now().hour <= 16:
                    today = today + datetime.timedelta(days=1)
            self.night = 'n' + today.strftime('%Y%m%d')

    #set up logger object
    def setup_logger(self):
            
            self.logger = logging.getLogger(self.logger_name)
            formatter = logging.Formatter(fmt="%(asctime)s [%(filename)s:%(lineno)s - %(funcName)20s()] %(levelname)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
            log_path = self.base_directory + '/log/' + self.night
            if os.path.exists(log_path) == False:
                    os.mkdir(log_path)
            fileHandler = logging.FileHandler(log_path + '/' + self.logger_name +'.log', mode='a')
            fileHandler.setFormatter(formatter)
            streamHandler = logging.StreamHandler()
            streamHandler.setFormatter(formatter)

            #clear handlers before setting new ones
            self.logger.handlers = []
            
            self.logger.setLevel(logging.DEBUG)
            self.logger.addHandler(fileHandler)
            self.logger.addHandler(streamHandler)

    # interpolate the lookup table for a given resistance to derive the temp
    # https://www.picotech.com/download/manuals/USBPT104ProgrammersGuide.pdf
    def ohm2temp(self,ohm):
        reftemp = np.linspace(-50,200,num=251)
        refohm = np.loadtxt('C:\minerva-control\minerva_library\pt100.dat')
        f = interp1d(refohm,reftemp)#,kind='cubic')
        try: temp = f(ohm)[()]
        except: temp = None
        return temp

    def resistance(self,calib,m):
        resistance = calib*(m[3]-m[2])/(m[1]-m[0])/1000000.0
        return resistance

    def logtemp(self):
        
        self.sock.settimeout(5.0)
        self.sock.gettimeout()

        self.logger.info("Sending data lock")

        self.sock.sendto("lock",(self.ip,self.port))
        val = self.sock.recv(2048)
        if 'Lock Success' not in val:
            self.logger.error("Error locking the data logger to this computer: " + val)

        self.logger.info("Connecting to the data logger")
        self.sock.connect((self.ip,self.port))
        
        # Calibration data
        self.logger.info("Getting calibration data")
        self.sock.send("32".decode('hex'))
        val = self.sock.recv(2048)
        cal = struct.unpack_from('<8ciiii',val,offset=36)
        caldate = ''.join(cal[0:7])
        self.logger.info("Temperature sensors calibrated on " + caldate)
        caldata = cal[8:12]

        self.logger.info("Starting data collection")
        self.sock.send("31".decode('hex') + "ff".decode('hex'))
        val = self.sock.recv(2048)
        if "Converting" not in val:
            self.logger.error("Failed to begin data collection")
        time.sleep(1.0)

        ndx = {
            '\x00': 0,
            '\x04': 1,
            '\x08': 2,
            '\x0c': 3,
            }
            
        while True:
            try:
                val = self.sock.recv(2048)

                if "Alive" in val:
                    pass
                elif "PT104" in val:
                    pass
                elif len(val) <> 20:
                    self.logger.error("Unexpected return string: " + val)
                else:
                    raw = struct.unpack('>cicicici',val)
                    meas = [float(raw[1]),float(raw[3]),float(raw[5]),float(raw[7])]

                    ohm = self.resistance(caldata[ndx[raw[0]]], meas)
                    temp = self.ohm2temp(ohm)

                    # log the temperature
                    filename = self.base_directory + '/log/' + self.night + '/temp' + str((int(self.num)-1)*4 + ndx[raw[0]] + 1) + '.log'
                    self.logger.info("Ohm=" + str(ohm) + ',temp=' + str(temp) + ',filename=' + filename + ',description='+self.description[ndx[raw[0]]])
                    with open(filename,'a') as f:    
                        f.write(str(datetime.datetime.utcnow()) + ',' + str(temp)+ ',' + self.description[ndx[raw[0]]] + '\n')

                # keep it alive
                self.sock.send("34".decode('hex'))
                time.sleep(0.1)
            except:
                self.logger.exception("error logging " + self.num)
    
            
if __name__ == "__main__":

    configs = ['PT100_1.ini','PT100_2.ini','PT100_3.ini','PT100_4.ini']
    pt100s = []
    threads = []
    n=0
    for config in configs:
        pt100s.append(PT100(config=config, base="C:/minerva-control/"))
        threads.append(threading.Thread(target = pt100s[n].logtemp))
        threads[n].start()
        n += 1

    ipdb.set_trace()
    
#    p1 = PT100(config="PT100_1.ini", base="C:/minerva-control/")
#    p2 = PT100(config="PT100_2.ini", base="C:/minerva-control/")
#    p3 = PT100(config="PT100_3.ini", base="C:/minerva-control/")
#    p4 = PT100(config="PT100_4.ini", base="C:/minerva-control/")
#    p3.logtemp()

    ipdb.set_trace()

    

    p3.sock.settimeout(5.0)
    p3.sock.gettimeout()

    p3.logger.info("Sending data lock")

    p3.sock.sendto("lock",(p3.ip,p3.port))
    val = p3.sock.recv(2048)
    if 'Lock Success' not in val:
        p3.logger.error("Error locking the data logger to this computer: " + val)

    p3.logger.info("Connecting to the data logger")
    p3.sock.connect((p3.ip,p3.port))
    
    # Calibration data
    p3.logger.info("Getting calibration data")
    p3.sock.send("32".decode('hex'))
    val = p3.sock.recv(2048)
    cal = struct.unpack_from('<8ciiii',val,offset=36)
    caldate = ''.join(cal[0:7])
    p3.logger.info("Temperature sensors calibrated on " + caldate)
    caldata = cal[8:12]

    p3.logger.info("Starting data collection")
    p3.sock.send("31".decode('hex') + "ff".decode('hex'))
    val = p3.sock.recv(2048)
    if val <> "Converting":
        p3.logger.error("Failed to begin data collection")
    time.sleep(1.0)

    ndx = {
        '\x00': 0,
        '\x04': 1,
        '\x08': 2,
        '\x0c': 3,
        }
        
    while True:
        try:
            val = p3.sock.recv(2048)
            raw = struct.unpack('>cicicici',val)
            meas = [float(raw[1]),float(raw[3]),float(raw[5]),float(raw[7])]

            ohm = p3.resistance(caldata[ndx[raw[0]]], meas)
            temp = p3.ohm2temp(ohm)
            print p3.description[ndx[raw[0]]], ohm, temp

#            # log the temperature
#            with open('temp' + str((self.num-1)*4 + ndx[raw[0]]]) + '.log','a') as f:
#                f.write(datetime.datetime.utcnow() + ',' + str(temp)+ ',' + self.description[ndx[raw[0]]])

            # keep it alive
            p3.sock.send("34".decode('hex'))
            time.sleep(0.1)
        except: pass