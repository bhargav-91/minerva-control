import sys
import os
import socket
import logging
import time
import threading
import datetime
from configobj import ConfigObj
sys.dont_write_bytecode = True

from si.client import SIClient
from si.imager import Imager
from minerva_library import dynapower
import ipdb

# spectrograph control class, control all spectrograph hardware
class spectrograph:

	def __init__(self,config, base =''):

		self.config_file = config
		self.base_directory = base
		self.load_config()
		self.setup_logger()
		self.create_class_objects
		self.status_lock = threading.RLock()
		self.file_name = ''
		# threading.Thread(target=self.write_status_thread).start()
	#load configuration file
	def load_config(self):
	
		try:
			config = ConfigObj(self.base_directory + '/config/' + self.config_file)
			self.ip = config['SERVER_IP']
			self.port = int(config['SERVER_PORT'])
			self.logger_name = config['LOGNAME']
			self.exptypes = {'Template':0,
                                         'Flat':0,
                                         'Arc':0,
                                         'FiberArc': 0,
                                         'FiberFlat':0,
                                         'Bias':0,
                                         'Dark':0,
                                         }

			# reset the night at 10 am local                                                                                                 
                        today = datetime.datetime.utcnow()
                        if datetime.datetime.now().hour >= 10 and datetime.datetime.now().hour <= 16:
                                today = today + datetime.timedelta(days=1)
                        self.night = 'n' + today.strftime('%Y%m%d')

		except:
			print('ERROR accessing configuration file: ' + self.config_file)
			sys.exit()

	#set up logger object
	def setup_logger(self,night='dump'):
		
		log_path = self.base_directory + '/log/' + night
                if os.path.exists(log_path) == False:os.mkdir(log_path)

                fmt = "%(asctime)s [%(filename)s:%(lineno)s - %(funcName)s()] %(levelname)s: %(message)s"
                datefmt = "%Y-%m-%dT%H:%M:%S"

                self.logger = logging.getLogger(self.logger_name)
                self.logger.setLevel(logging.DEBUG)
                formatter = logging.Formatter(fmt,datefmt=datefmt)
                formatter.converter = time.gmtime

                #clear handlers before setting new ones                                                                               
                self.logger.handlers = []

                fileHandler = logging.FileHandler(log_path + '/' + self.logger_name + '.log', mode='a')
                fileHandler.setFormatter(formatter)
                self.logger.addHandler(fileHandler)

                # add a separate logger for the terminal (don't display debug-level messages)                                         
                console = logging.StreamHandler()
                console.setFormatter(formatter)
                console.setLevel(logging.INFO)
                self.logger.setLevel(logging.DEBUG)
                self.logger.addHandler(console)
		
	def create_class_objects(self):
                self.dynapower1 = dynapower.dynapower(self.night,configfile='minerva_class_files/dynapower_1.ini')
                self.dynapower2 = dynapower.dynapower(self.night,configfile='minerva_class_files/dynapower_2.ini')
		
	#return a socket object connected to the camera server
	def connect_server(self):
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.settimeout(1)
			s.connect((self.ip, self.port))
			self.logger.info('successfully connected to spectrograph server')
		except:
			self.logger.error('failed to connect to spectrograph server')
		return s
	#send commands to camera server running on telcom that has direct control over instrument
	def send(self,msg,timeout):
		try:
			s = self.connect_server()
			s.settimeout(3)
			s.sendall(msg)
		except:
			self.logger.error("connection lost")
			return 'fail'
		try:
			s.settimeout(timeout)
			data = s.recv(1024)
		except:
			self.logger.error("connection timed out")
			return 'fail'
		data = repr(data).strip("'")
		if data.split()[0] == 'success':
			self.logger.info("command completed")
		else:
			self.logger.error("command failed")
		return data
	#get camera status and write into a json file with name == (self.logger_name + '.json')
	def write_status(self):
		res = self.send('get_status none',5).split(None,1)
		if res[0] == 'success':
			self.status_lock.acquire()
			status = open(self.base_directory+'/status/' + self.logger_name+ '.json','w')
			status.write(res[1])
			status.close()
			self.status_lock.release()
			self.logger.info('successfully wrote status')
			return True
		else:
			self.logger.error('failed to write status')
			return False
	#loop function used in a separate status thread
	def write_status_thread(self):
		while True:
			self.wite_status()
			time.sleep(10)
	#set path for which new images will be saved,if not set image will go into dump folder
	def set_data_path(self,night='dump'):
		
		self.night = night
		if self.send('set_data_path ' + night,3) == 'success':
			self.logger.info('successfully set datapath') 
			return True
		else:
			self.logger.error('failed to set datapath')
			return False
	#get index of new image
	def get_index(self):
		res = self.send('get_index none',5).split()
		if res[0] == 'success': return int(res[1])
		else: return -1
	def get_filter_name(self):
		return self.send('get_filter_name none',5)
	def check_filters(self):
		filter_names = self.get_filter_name().split()
		if len(filter_names) != len(self.filters)+1:
			return False
		for i in range(len(self.filters)):
			if self.filters[i] != filter_names[i+1]:
				return False
		return True
	#ask remote telcom to connect to camera
	def connect_camera(self):
		if (self.send('connect_camera none',30)).split()[0] == 'success':
			if self.check_filters()==False:
				self.logger.error('mismatch filter')
				return False
			self.logger.info('successfully connected to camera')
			return True
		else:
			self.logger.error('failed to connected to camera')
			return False
			
	def set_binning(self):
		if self.send('set_binning ' + self.xbin + ' ' + self.ybin, 5) == 'success': return True
		else: return False
		
	def set_size(self):
		if self.send('set_size '+ self.x1 + ' ' + self.x2 + ' ' + self.y1 + ' ' + self.y2,5) == 'success': return True
		else: return False
			
	def settle_temp(self):
		threading.Thread(target = self.send,args=('settle_temp ' + self.setTemp,910)).start()
		
	#start exposure
	def expose(self, exptime=1.0, exptype=0, filterInd=1):

        	host = "localhost"
                port = 2055
                client = SIClient (host, port)
                self.logger.info("Connected to SI client")

                imager = Imager(client)
                self.logger.info("Connected to SI imager")
                imager.nexp = 1		        # number of exposures
                imager.texp = exptime		# exposure time, float number
                imager.nome = "image"		# file name to be saved
                imager.dark = False		# dark frame?
                imager.frametransfer = False	# frame transfer?
                imager.getpars = False		# Get camera parameters and print on the screen

                imager.do()

                return self.save_image(self.file_name)
 
	#block until image is ready, then save it to file_name
      	def set_file_name(self,file_name):
        	if self.send('set_file_name ' + file_name,30) == 'success': return True
		else: return False
	def save_image(self,file_name):
        	if self.send('save_image ' + file_name,30) == 'success': return True
		else: return False
	def image_name(self):
                return self.file_name
	#write fits header for self.file_name, header_info must be in json format
	def write_header(self, header_info):
		if self.file_name == '':
                        self.logger.error("self.file_name is undefined")
			return False
		i = 800
		length = len(header_info)
		while i < length:
			if self.send('write_header ' + header_info[i-800:i],3) == 'success':
				i+=800
			else:
                                self.logger.error("write_header command failed")
				return False

		if self.send('write_header_done ' + header_info[i-800:length],10) == 'success':
			return True
		else:
                        self.logger.error("write_header_done command failed")
			return False

        def recover(self):
                sys.exit()
        
	def take_image(self,exptime=1,objname='test'):

                exptime = int(float(exptime)) #python can't do int(s) if s is a float in a string, this is work around
		#put together file name for the image
		ndx = self.get_index()
		if ndx == -1:
			self.logger.error("Error getting the filename index")
			ipdb.set_trace()
			self.recover()
			return self.take_image(exptime=exptime, filterInd=filterInd,objname=objname)

		self.file_name = self.night + "." + objname + "." + str(ndx).zfill(4) + ".fits"
		self.logger.info('Start taking image: ' + self.file_name)
		#chose exposure type
		if objname in self.exptypes.keys():
			exptype = self.exptypes[objname] 
		else: exptype = 1 # science exposure

#		#chose appropriate filter
#		if filterInd not in self.filters:
#			self.logger.error(telescope_name + "Requested filter (" + filterInd + ") not present")
#			return 'false'
                # configure spectrograph
                # turn on I2 heater
                # move I2 stage
                # turn on/off all lamps
                # open/close calibration shutter
                # Move calibration FW
                # begin exposure meter

                self.set_file_name(self.file_name)
		
		if self.expose(exptime=exptime):
			self.logger.info('Finished taking image: ' + self.file_name)
			self.nfailed = 0 # success; reset the failed counter
			return
		else: 
        		self.logger.error('Failed to save image: ' + self.file_name)
			self.file_name = ''
			self.recover()
			return self.take_image(exptime=exptime,objname=objname) 

        def vent(self):
                # close the pump valve
                self.dynapower.off('pumpvalve')

                # turn off the pump
                self.dynapower.off('pump')

                if self.specgauge.pressure() < 500:
                    mail.send("The spectrograph is pumped and attempting to vent!","Manual login required to continue")
                    self.logger.error("The spectrograph is pumped and attempting to vent; manual login required to continue")
                    ipdb.set_trace()            

                # open the vent valve
                self.dynapower.on('ventvalve')

                t0 = datetime.datetime.utcnow()
                elapsedtime = 0.0
                while self.specgauge.pressure() < 500:
                    elapsedtime = (datetime.datetime.utcnow() - t0).total_seconds() 
                    self.logger.info('Waiting for spectrograph to vent (Pressure = ' + str(specgauge.pressure()) + '; elapsed time = ' + str(elapsedtime) + ' seconds)')
                    if elapsedtime < timeout:
                        time.sleep(5)
                    else:
                        self.logger.error("Error venting the spectrograph")
                        return

                self.logger.info("Venting complete")
 
        # pump down the spectrograph (during the day)     
        def pump(self):

                timeout = 300

                # close the pump valve
                self.dynapower.off('pumpvalve')

                # turn on the pump
                self.dynapower.on('pump')

                if self.get_vacuum_pressure() > 500:
                    mail.send("The spectrograph is at atmosphere!","Manual login required to continue")
                    self.logger.error("The spectrograph is at atmosphere! Manual login required to continue")
                    ipdb.set_trace()

                # wait until the guage reads < 100 ubar
                t0 = datetime.datetime.utcnow()
                elapsedtime = 0.0
                while self.get_pump_pressure() > 100.0:
                    elapsedtime = (datetime.datetime.utcnow() - t0).total_seconds() 
                    self.logger.info('Waiting for tube to pump down (Pressure = ' + str(pumpgauge.pressure()) + '; elapsed time = ' + str(elapsedtime) + ' seconds)')
                    if elapsedtime < timeout:
                        time.sleep(5)
                    else:
                        self.logger.error("Error pumping down the spectrograph")
                        return          
                        
                # open the pump valve
                self.dynapower.on('pumpvalve')

        def cell_heater_on(self):
                response = self.send('cell_heater_on None',5)
                return float(response.split()[1].split('\\')[0])               

        def cell_heater_off(self):
                response = self.send('cell_heater_off None',5)
                return float(response.split()[1].split('\\')[0])                        

        def cell_heater_temp(self):
                response = self.send('cell_heater_temp None',5)
                return float(response.split()[1].split('\\')[0])

        def cell_heater_set_temp(self, temp):
                response = self.send('cell_heater_set_temp ' + str(temp),5)
                return float(response.split()[1].split('\\')[0])

        def cell_heater_get_set_temp(self):
                response = self.send('cell_heater_get_set_temp None',5)
                return float(response.split()[1].split('\\')[0]) 

        # close the valves, hold the pressure (during the night)
        def hold(self):

                # make sure the vent valve is closed
                self.dynapower.off('ventvalve')

                # close the pump valve
                self.dynapower.off('pumpvalve')

                # turn off the pump
                self.dynapower.off('pump')
			
	def get_vacuum_pressure(self):
                response = self.send('get_vacuum_pressure None',5)
                if response == 'fail':
                        return 'UNKNOWN'
                ipdb.set_trace()
		return float(response.split()[1].split('\\')[0])

        ### doesn't work!###
        def get_atmospheric_pressure(self):
                response = self.send('get_atmospheric_pressure None',5)
                return float(response.split()[1].split('\\')[0])

        
	
if __name__ == '__main__':
	
	base_directory = '/home/minerva/minerva-control'
        if socket.gethostname() == 'Kiwispec-PC': base_directory = 'C:/minerva-control'
	test_spectrograph = spectrograph('spectrograph.ini',base_directory)
	while True:
		print 'spectrograph_control test program'
		print ' a. take_image'
		print ' b. expose'
		print ' c. set_data_path'
		print ' d. set_binning'
		print ' e. set_size'
		print ' f. settle_temp'
		print ' g. vacuum pressure'
		print ' h. atmospheric pressure'
		print ' i. dummy'
		print '----------------------------'
		choice = raw_input('choice:')

		if choice == 'a':
			pass
		elif choice == 'b':
			test_spectrograph.expose()
		elif choice == 'c':
			test_spectrograph.set_data_path()
		elif choice == 'd':
			test_spectrograph.set_binning()
		elif choice == 'e':
			test_spectrograph.set_size()
		elif choice == 'f':
			test_spectrograph.settle_temp()
		elif choice == 'g':
			print test_spectrograph.get_vacuum_pressure()
		elif choice == 'h':
			print test_spectrograph.get_atmospheric_pressure()
		else:
			print 'invalid choice'
			
			
	
