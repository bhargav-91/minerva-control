#Minerva system main routine
#create master control object and run one of the observing scripts
import matplotlib
matplotlib.use('Agg')
import sys, os
sys.dont_write_bytecode = True
from minerva_library import control  
from minerva_library import rv_control
from minerva_library import utils
import datetime

#-------------------
import threading
import time, json, copy, ipdb
import numpy as np
#================#

#  At 4:00 run this script.


def SetupTech(minerva, telescope, camera):

    if not telescope.initialize(tracking=False, derotate=False):
        telescope.recover(tracking=False, derotate=False)

    telescope.home()    
    #S Finally (re)park the telescope.
    telescope.park()     

    # wait for the camera to cool down
    camera.cool()
   
    return


def PhotCalib(minerva, CalibInfo, telid, checkiftime=True):
    #  Photometric Calibrations

    # Take biases and darks
    # wait until it's darker to take biases/darks
    readtime = 10.0
        
    bias_seconds = CalibInfo['nbias']*readtime+CalibInfo['ndark']*sum(CalibInfo['darkexptime']) + CalibInfo['ndark']*readtime*len(CalibInfo['darkexptime']) + 600.0  # Extra 600 is to give it an extra 10 minutes just in case timing isn't perfect.
    biastime = minerva.site.sunset() - datetime.timedelta(seconds=bias_seconds)
    waittime = (biastime - datetime.datetime.utcnow()).total_seconds()
    if waittime > 0 and checkiftime:
        # Take biases and darks (skip if we don't have time before twilight)
        minerva.logger.info(telescope_name + 'Waiting until darker before biases/darks (' + str(waittime) + ' seconds)')
        time.sleep(waittime)
        #S Re-initialize, and turn tracking on.
        minerva.doBias(CalibInfo['nbias'],telid)
        minerva.doDark(CalibInfo['ndark'], CalibInfo['darkexptime'],telid)
    return

def startSkyFlats(minerva, telescope, dome, CalibInfo):
    # Take Evening Sky flats
    #S Initialize again, but with tracking on.
    if not telescope.initialize(tracking=True, derotate=True):
        telescope.recover(tracking=True, derotate=True) 

    
    flatFilters = CalibInfo['flatFilters'] 
    minerva.doSkyFlat(flatFilters, False, CalibInfo['nflat'],telescope.id)
        
    # Wait until nautical twilight ends
    timeUntilTwilEnd = (minerva.site.NautTwilEnd() - datetime.datetime.utcnow()).total_seconds()
    if timeUntilTwilEnd > 0:
        minerva.logger.info('Waiting for nautical twilight to end (' + str(timeUntilTwilEnd) + 'seconds)')
        time.sleep(timeUntilTwilEnd)
        
    while not dome.isOpen() and datetime.datetime.utcnow() < minerva.site.NautTwilBegin() and datetime.datetime.utcnow() < minerva.site.NautTwilEnd():
        minerva.logger.info('Enclosure closed; waiting for conditions to improve')
        time.sleep(60)
    
    
    return



# acquisition == 2 min , readtime_phot = 7 sec, readtime_spec = 21.6 sec  # acquisition ~ slewing, focusing, fine pointing
# duration ==  acquisition + np.sum( num*(exptime + readtime)  )
# save duration in its list or dictionary
def Acq_Exp_RdO(acquisition, target_dict, readtime):
     '''
     Calculate the total amount of time (in seconds) being used by CCD activity and telescope movements
     '''
     filters = target_dict['filter']
     num_exposures = target_dict['num'][0]
     exptime = np.float(target_dict['exptime'][0])

     return datetime.timedelta( seconds = acquisition + np.sum( num_exposures*(exptime + readtime) ) )
     
     
          
          
          
          


def get_States(minerva, tel_phot_targets):
    '''
    For a given expected starttime, record all of the telescopes that want to observe at that time. Also, arrange the exp_starttimes in order (with their corresponding telescope(s) attached to that ordering)

    What if two different targets wanted to start being observed at the exact same expected starttime?
    -- Then I'd have to account for the 'name' of the target as well as its exp_starttime.


    Parameters
    ----------
    minerva: list

    tel_phot_targets: dictionary
                      The target schedule based on the telescope and then the index of observations (probably in chrono order, but I will not assume that)

    Return
    ------
    states_dict: dictionary

    '''
    Teles_starts = {}
    Teles_used = {}
    Teles_target_info = {}

    onePhot_tele = None
    for telescope in minerva.telescopes:
        if tel_phot_targets[telescope.id] != None:
            onePhot_tele = telescope.id 
            break



    if onePhot_tele != None:
        my_field_names = copy.copy(tel_phot_targets[onePhot_tele][0].keys()) # Any telescopes[index] (except the 'None' ones) and any ind_target should work
        my_field_names.pop( my_field_names.index('exp_starttime')  )

        all_starttimes = []
        phot_teles = []
        for telescope in minerva.telescopes:

            if tel_phot_targets[telescope.id] != None: # there actually is a photometric target for this telescope

                Teles_target_info[telescope.id] = {}
            
                Teles_starts[telescope.id] = []
                for ind_target in xrange(len(tel_phot_targets[telescope.id])):
                
                    Teles_starts[telescope.id].append( tel_phot_targets[telescope.id][ind_target]['exp_starttime'] )
                
                    # record all other original info
                    for title in my_field_names:
                        if ind_target == 0:  #if title not in Teles_target_info[telescope.id].keys():  # this entire script currently depends on every telescope dictionary and each of their targets having the same titles/fields and number of titles/fields
                            Teles_target_info[telescope.id][title] = []
                        
                        Teles_target_info[telescope.id][title].append( tel_phot_targets[telescope.id][ind_target][title] )

                        
#                Teles_used[telescope.id] = list(np.ones(len( Teles_starts[telescope.id] ), dtype='int')*int(telescope.num)) # now that I use telescope.num, this might be unnecessarily redundant
                Teles_used[telescope.id] = list( np.repeat( telescope.id, len(Teles_starts[telescope.id]) ) )
                phot_teles += Teles_used[telescope.id]
                all_starttimes += Teles_starts[telescope.id]
                # Both all_starttimes and phot_teles are now lists that correspond to ALL (no matter the telescope) exp_starttimes                
            
            
        fields = []
        for title in my_field_names:
            if type(Teles_target_info[onePhot_tele][title][0])==list:
                fields.append([])
                for telescope in minerva.telescopes:
                    f= Teles_target_info[onePhot_tele][title]                    
                    fields[-1] +=f
            else:
                fields.append( list(np.concatenate( [ Teles_target_info[telescope.id][title] for telescope in minerva.telescopes if tel_phot_targets[telescope.id] != None ] )) )
            # Now every field has its own list that corresponds to ALL (no matter the telescope) exp_starttimes

        all_tuples =[]

        # The different telescope dictionaries should have the same exp_starttime for observing the same object.  Such duplicates should be accounted for.
        phot_teles = np.array(phot_teles) # for indexing multiple indices
        for s_time_ind in xrange(len(all_starttimes)):
            dup_inds = np.where( np.array(all_starttimes) == all_starttimes[s_time_ind] )[0]

            
            if s_time_ind == dup_inds[0]: # if an exp_starttime has a multiplicity of 1, then go. if an exp_starttime has a multiplicity > 1 but this is the first time is has occurred in the FOR loop, then go.
                single_fields = []
                for field_ind in xrange(len(fields)):
                    fields[field_ind] = np.array(fields[field_ind])
                    single_fields.append( list( fields[field_ind][dup_inds] ) ) # shouldn't the same field from different telescopes (for the same exp_starttime) be the exact same value?  --- One exp_starttime could have overlapped with another telescope's exp_starttime for a different target.  Or two telescopes can be told to observe differenct phot objects simultaneously
                
                all_tuples.append( tuple( [ all_starttimes[s_time_ind], list(phot_teles[dup_inds]) ]+single_fields ) ) # a list of tuples with each element of the tuple corresponding to a field name: 'exp_starttime', 'Teles', etc.
            

        # Arrange in chronological order
    
        prep_formats = []
        for field_ind in xrange(len(all_tuples[0])):
            dat_type = str(np.dtype(type( all_tuples[0][field_ind] )))
            if dat_type == '|S0': dat_type = '|S10'  # for some reason, numpy does not recognize the |S0 string format
            prep_formats.append( dat_type )
    
        #prep_array = np.array( all_tuples, dtype= { 'names': ['exp_starttimes','Telescope_lists']+my_field_names,'formats': [datetime.datetime,'object'] } )
        prep_array = np.array( all_tuples, dtype= { 'names': ['exp_starttime','Teles']+my_field_names,'formats': prep_formats } )
        sorted_array = np.sort( prep_array, order='exp_starttime' )

        states_dict = {}
    
        # IF the very first 'exp_starttime' is after minerva.site.NautTwilEnd() then make the first state at that time.
        # IF the very last 'exp_endtime' is after minerva.site.NautTwilBegin() then make the last state at that time.
        if sorted_array['exp_starttime'][0] > minerva.site.NautTwilEnd():  # Won't it always find the very next sunset and not the one that I truly want ? -- NO.  Because of the minerva object, it will always get the closest, most relevant twilight ending or beginning
            states_dict['exp_starttime'] = [ minerva.site.NautTwilEnd() ]
            for title in ['Teles']+my_field_names:
                states_dict[title] = [None] 
        
        for title in ['exp_starttime','Teles']+my_field_names: #sorted_array.dtype.names:
        
            try: # possibly because of the NautTwilEnd condition
                states_dict[title] += list( sorted_array[title] )
            except KeyError:
                states_dict[title] = list( sorted_array[title] ) # command what may be a list to be a list does not change anything. 
            
            
    else: # No telescopes have a phot schedule for tonight

        states_dict = {}
        states_dict['exp_starttime'] = [minerva.site.NautTwilEnd()]
        states_dict['Teles'] = [None]
        
    # Caveats:
    # 1) Every phot target must have the same fields filled out in their dictionaries.

                
    return states_dict 




def omniObserve(minerva, states):
    '''
    Start all observations.
    
    Parameters
    ----------


    Return
    ------

    '''

    for state_ind in xrange(len(states['exp_starttime'])):

        threads = []

        phot_teles_id = copy.copy( states['Teles'][state_ind] ) 
        rv_teles_id = []
        for telescope in minerva.telescopes: rv_teles_id.append(telescope.id)
        
        if phot_teles_id != None: 
                  
            #  call the " self.doScience(target,telescope_num) "
            phot_target_teles = {}
            for title in states.keys():  
                phot_target_teles[title] = states[title][state_ind]  
                
                    
            phot_target={}
            counter = 0
            for tele in phot_teles_id:
                for title in states.keys(): 
                    if title !="exp_starttime": 
                        phot_target[title] = phot_target_teles[title][counter]
                    else:
                        phot_target[title] = phot_target_teles[title]

                counter+=1 # index for the telescopes
                threads.append( threading.Thread( target = minerva.doScience, args = (phot_target, tele) ))
                threads[-1].name = 'Phot_Obs_'+str(tele)
                threads[-1].start()

            for tel in phot_teles_id: rv_teles_id.pop( rv_teles_id.index(tel) )

            
        if state_ind < len(states['exp_starttime'])-1:
            time_thresh = states['exp_starttime'][state_ind + 1] # upcoming state change
            
        elif state_ind == len(states['exp_starttime'])-1:
            time_thresh = minerva.site.NautTwilBegin()
            
        minerva.logger.info('Beginning nightly loop')
        remaining_time = (time_thresh - datetime.datetime.utcnow()).total_seconds()

        while remaining_time > 0.0:
        
            # check the time remaining before the next state change and know which telescope(s) will operate then
            minerva.logger.info('Time left in the night ' + str(remaining_time) + ' seconds')            

            # tell the dynamic scheduler the remaining time gap
            RV_target =  minerva.scheduler.choose_target(remaining_time=remaining_time,logger=minerva.logger, timeof=datetime.datetime.utcnow())
            
            # Check if dynamic scheduler provided any targets
            if len(RV_target) > 0:
                minerva.logger.info('Taking spectrum of ' + RV_target['name'])
    
                # CALL RV observation
                # The remaining telescopes will always collect RVs on the same target
                threads.append( threading.Thread( target = rv_control.doSpectra, args = (minerva,RV_target,rv_teles_id) ))
                threads[-1].name = 'RV_Obs'
                threads[-1].start()
                minerva.logger.info('RV thread is activated.')

                # tell the scheduler that we observed the target
                for ii,target in enumerate(minerva.scheduler.target_list):
                    if target['name'] == RV_target['name']:
                        if 'observed' in minerva.scheduler.target_list[ii].keys(): 
                            minerva.scheduler.target_list[ii]['observed'] += 1
                        else:
                            minerva.scheduler.target_list[ii]['observed'] = 1
                        minerva.scheduler.target_list[ii]['last_obs'] = datetime.datetime.utcnow()
                        break

            else:
                minerva.logger.info("The scheduler did not return any viable RV targets")
                time.sleep(5.0)


            t_names = [threads[p].name for p in xrange(len(threads))]
            # Check if phot threads are dead.
            for telescope in minerva.telescopes:
                if 'Phot_Obs_'+telescope.id in t_names:
            
                    if threads[np.where(np.array(t_names)=='Phot_Obs_'+telescope.id)[0][0]].isAlive() != True:
                                                 
                        minerva.logger.info('Photometry T'+telescope.id+' thread is now dead.')
                        
                        threads.pop( np.where(np.array(t_names)=='Phot_Obs_'+telescope.id)[0][0] )
                         
            if len(RV_target) > 0: threads[-1].join() # wait until RV thread is done/dead.
            time.sleep(1)
            remaining_time = (time_thresh - datetime.datetime.utcnow()).total_seconds()


        minerva.logger.info('Waiting for telescope threads to finish')
        for p in xrange(len(threads)):
            threads[p].join()  # if no photometry was taken, then the rv threads will simply be re-joined.

    
    return






if __name__ == '__main__':  # do a bunch of threading stuff

    try: utils.killmain()
    except: pass

    base_directory = '/home/minerva/minerva-control'
    minerva = control.control('control.ini',base_directory)

    threads = []

    for telescope in minerva.telescopes:
        # Prep for Night
        camera = utils.getCamera(minerva,telescope.id)

        #set up night's directory
        minerva.prepNight(telescope)
        scheduleFile = minerva.base_directory + '/schedule/' + minerva.site.night + '.' + telescope.id + '.txt'
        utils.scheduleIsValid(scheduleFile, email=True, logger=minerva.logger)
    

        # Setup tech thread
        threads.append(  threading.Thread( target = SetupTech, args=(minerva, telescope, camera) ) )
        threads[-1].name = 'SetupTech_'+str(telescope.id)
        threads[-1].start()
        
        # End FOR loop

    # Wait until all threads are done because if this telescope's homing is not complete, 
    # then the skyflats thread (which checks to see if the homing is complete)
    # will try to home the telescope if it sees that it is not done homing.  
    # This makes 2 functions trying to home the telescope at the same time. 
    for p in np.arange(len(threads)):
        minerva.logger.info("Waiting for " + threads[p].name + " to finish")
        threads[p].join()
        

    threads=[]

    # Spectroscopic Calibration

    # if before the end of twilight, do calibrations
    if datetime.datetime.utcnow() < minerva.site.NautTwilEnd():
        rv_control.backlight(minerva)
         
        # by default, checkiftime = True. This is just here as a reminder
        kwargs ={'checkiftime': True}
        threads.append( threading.Thread( target = minerva.specCalib, args=(),kwargs=kwargs ) )
        threads[-1].name = 'SpecCalib'
        threads[-1].start()


    for telescope in minerva.telescopes:

        telescope = utils.getTelescope(minerva,telescope.id)  
        CalibInfo,CalibEndInfo = minerva.loadCalibInfo(telescope.id)

        if CalibInfo != None and CalibEndInfo !=None:

            # Photometry Calibration thread
            if datetime.datetime.utcnow() < minerva.site.NautTwilEnd():

                # by default, checkiftime = True. This is just here as a reminder
                kwargs = {'checkiftime':True}
                threads.append(  threading.Thread( target = PhotCalib, args=(minerva, CalibInfo, telescope.id), kwargs=kwargs ) )
                threads[-1].name = telescope.id
                threads[-1].start()                  
        

    for p in np.arange(len(threads)):
        threads[p].join()

    # Now do Domes and Skyflats
    threads=[]
    for telescope in minerva.telescopes:

        CalibInfo,CalibEndInfo = minerva.loadCalibInfo(telescope.id)

        # Prepare Domes before taking Sky flats
        dome = utils.getDome(minerva, telescope.id)

 
        sunfile = minerva.base_directory + '/minerva_library/sunOverride.txt'
        if os.path.exists(sunfile): os.remove(sunfile)

        with open(minerva.base_directory + '/minerva_library/aqawan1.request.txt','w') as fh:
            fh.write(str(datetime.datetime.utcnow()))

        with open(minerva.base_directory + '/minerva_library/aqawan2.request.txt','w') as fh:
            fh.write(str(datetime.datetime.utcnow()))

        if CalibInfo != None and CalibEndInfo != None:
            if datetime.datetime.utcnow() < minerva.site.NautTwilEnd():
                # Skyflats thread
                threads.append(  threading.Thread( target = startSkyFlats, args=(minerva, telescope, dome, CalibInfo) ) )
                threads[-1].name = telescope.id
                threads[-1].start()                  
     
        # End FOR loop
        

       
    tel_p_targets = {}
    for telescope in minerva.telescopes:

        try:
            with open(minerva.base_directory + '/schedule/' + minerva.site.night + '.' + telescope.id + '.txt', 'r') as targetfile:
                next(targetfile) # skip both calibration headers
                next(targetfile)

                p_targets = []
                for line in targetfile: 
                    target = minerva.parseTarget(line) 
                    
                    if target <> -1:  # only works for Python 2
                        # truncate the start and end times so it's observable: elevation (above ~20 degrees) and airmass (X < 3 or 2)
                        target = utils.truncate_observable_window(minerva.site, target)
                             
                        # The target dictionary's start and end times should be in datetime.datetime format now
                        
                        if target['starttime'] < target['endtime']:
                            p_targets.append( target )
                            # starttime and endtime should only represent when the object is observable
                             
                tel_p_targets[telescope.id] = p_targets
              
        except IOError: # there is no photometry target file
               
            # record the telescope so that when the night begins, the dynamic scheduler will know which telescope(s) are free
            tel_p_targets[telescope.id] =  None
               
# Even if there is a photometry schedule for a telescope, we may not want (or be able) to use that telescope so I don't include such a telescope in the dictionary

            
    # Calculate the duration times between photometry targets
    # Calculate the expected start and end times of the photometric observations
    for telescope in minerva.telescopes: 
        # check for photometry targets in the telescope target [list]
        if tel_p_targets[telescope.id] != None: 
               
            for ind_target in xrange(len(tel_p_targets[telescope.id])):
                p_target = tel_p_targets[telescope.id][ind_target]  # without copy.copy, this ind_target dictionary will change whenever the p_target variable changes.  This only happens with one variable coupling at a time
                    
                if ind_target == 0:
                    
                    if p_target['starttime'] < minerva.site.NautTwilEnd(): # staying safe, but should not be necessary
                        p_target['exp_starttime'] = minerva.site.NautTwilEnd()
                              
                    else:
                        p_target['exp_starttime'] = p_target['starttime']

                        # Add expected endtime by accounting for the number of exposures, exposure time, filters, and acquisition
                        p_target['exp_endtime'] = p_target['exp_starttime'] + Acq_Exp_RdO(120.0, p_target, 7.0)

                        if p_target['exp_endtime'] > p_target['endtime']:
                            p_target['exp_endtime'] = p_target['endtime']

                        if p_target['exp_endtime'] > minerva.site.NautTwilBegin(): # if the exp_endtime is later than sunrise
                            p_target['exp_endtime'] = minerva.site.NautTwilBegin()
                         
                else:

                    # check previous expected endtime, if that overlaps with the current starttime then create expected starttime in target's dictionary
                    if p_target['starttime'] <= tel_p_targets[telescope.id][ind_target-1]['exp_endtime']:

                        p_target['exp_starttime'] = tel_p_targets[telescope.id][ind_target-1]['exp_endtime'] # It is okay to overlap because of the specified acquisition time, and the computer won't start acquiring the next target until the first one is finished--even if I tell it to do so.
                              
                    else:
                        p_target['exp_starttime'] = p_target['starttime']
                        
                                             
                    # After ascertaining expected starttime of this target, then determine expected endtime of this target
                    p_target['exp_endtime'] = p_target['exp_starttime'] + Acq_Exp_RdO(120.0, p_target, 7.0)

                    if p_target['exp_endtime'] > p_target['endtime']:
                        p_target['exp_endtime'] = p_target['endtime']

                    if p_target['exp_endtime'] > minerva.site.NautTwilBegin(): # if the exp_endtime is later than sunrise
                        p_target['exp_endtime'] = minerva.site.NautTwilBegin()

                              
                #tel_p_targets[telescope.id][ind_target] = p_target  # the updated dictionary is placed back in the list  # This should be unnecessary because I did not use copy.copy

                    
    # Get the states of change
    chrono_states = get_States(minerva, tel_p_targets)

    
    # Wait for the sky flats to finish
    for p in np.arange(len(threads)):
        threads[p].join()
         
    omniObserve(minerva, chrono_states)
    
    for tele in minerva.telescopes: minerva.endNight(tele,kiwispec=True)