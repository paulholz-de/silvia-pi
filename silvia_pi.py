#!/usr/bin/python

def pid_loop(dummy,state):
  import sys
  from time import sleep
  from math import isnan
  import Adafruit_GPIO as GPIO
  import Adafruit_GPIO.SPI as SPI
  import Adafruit_MAX31855.MAX31855 as MAX31855
  import PID as PID
  import config as conf

  def c_to_f(c):
    return c * 9.0 / 5.0 + 32.0

  sensor = MAX31855.MAX31855(spi=SPI.SpiDev(conf.spi_port, conf.spi_dev))

  rGPIO = GPIO.get_platform_gpio()
  rGPIO.setup(conf.he_pin, GPIO.OUT)
  rGPIO.output(conf.he_pin,0)

  pid = PID.PID(conf.P,conf.I,conf.D)
  pid.SetPoint = conf.set_temp
  pid.setSampleTime(conf.sample_time)

  nanct=0
  i=0
  j=0
  pidhist = [0.,0.,0.,0.,0.,0.,0.,0.,0.,0.]
  avgpid = 0.
  temphist = [0.,0.,0.,0.,0.]
  avgtemp = 0.
  hestat = 0

  print 'P =',conf.P,'I =',conf.I,'D =',conf.D,'Set Temp =',conf.set_temp
  print 'i tempf pidout pidavg pterm iterm dterm hestat'

  try:
    while True : # Loops 10x/second
      tempc = sensor.readTempC()
      tempf = c_to_f(tempc)
      temphist[i%5] = tempf
      avgtemp = sum(temphist)/len(temphist)

      if isnan(tempc) :
        nanct += 1
        if nanct > 100000 :
          rGPIO.output(conf.he_pin,0)
          break
        continue
      else:
        nanct = 0

      pid.update(avgtemp)
      pidout = pid.output
      pidhist[i%10] = pidout
      avgpid = sum(pidhist)/len(pidhist)

      if avgpid >= 100 :
        hestat = 1
      elif avgpid > 0 and avgpid < 100 and tempf < conf.set_temp :
        if i%10 == 0 :
          j=int((avgpid/10)+.5)
        if i%10 <= j :
          hestat = 1
        else :
          hestat = 0
      else:
        hestat = 0

      rGPIO.output(conf.he_pin,hestat) 

      state['i'] = i
      state['tempf'] = round(tempf,2)
      state['avgtemp'] = round(avgtemp,2)
      state['pidval'] = round(pidout,2)
      state['avgpid'] = round(avgpid,2)
      state['pterm'] = round(pid.PTerm,2)
      state['iterm'] = round(pid.ITerm * conf.I,2)
      state['dterm'] = round(pid.DTerm * conf.D,2)
      state['settemp'] = round(conf.set_temp,2)
      state['hestat'] = hestat

      print state

      i += 1
      sleep(conf.sample_time)

  finally:
    pid.clear
    rGPIO.output(conf.he_pin,0)
    rGPIO.cleanup()

def rest_server(dummy,state):
  from bottle import route, run, template, get, post, request, static_file
  from subprocess import call
  import config as conf

  @route('/')
  def docroot():
    return static_file('index.html',conf.wwwdir)

  @route('/<filename>')
  def servfile(filename):
    return static_file(filename,conf.wwwdir)

  @route('/curtemp')
  def curtemp():
    return str(state['avgtemp'])

  @get('/settemp')
  def settemp():
    return str(state['settemp'])

  @post('/settemp')
  def post_settemp():
    settemp = request.forms.get('settemp')
    if settemp > 200 and settemp < 265 :
      state['settemp'] = settemp
      return str(settemp)
    return str(-1)

  @route('/allstats')
  def allstats():
    return dict(state)

  @route('/restart')
  def restart():
    call(["reboot"])
    return '';

  @route('/healthcheck')
  def healthcheck():
    return 'OK';

  run(host='0.0.0.0',port=conf.port)

if __name__ == '__main__':
  from multiprocessing import Process, Manager
  from time import sleep
  from urllib2 import urlopen
  import config

  manager = Manager()
  pidstate = manager.dict()

  p = Process(target=pid_loop,args=(1,pidstate))
  p.daemon = True
  p.start()

  r = Process(target=rest_server,args=(1,pidstate))
  r.daemon = True
  r.start()

  #Start Watchdog loop
  piderr = 0
  weberr = 0
  weberrflag = 0
  urlhc = 'http://localhost:'+str(config.port)+'/healthcheck'

  sleep(3)
  lasti = pidstate['i']
  sleep(1)

  while True:
    curi = pidstate['i']
    if curi == lasti :
      piderr = piderr + 1
    else :
      piderr = 0

    lasti = curi

    if piderr > 9 :
      print 'ERROR IN PID THREAD, RESTARTING'
      p.terminate()
      sleep(2)
      p.run()
      sleep(2)

    try:
      hc = urlopen(urlhc,timeout=2)
    except:
      weberrflag = 1
    else:
      if hc.getcode() != 200 :
        weberrflag = 1

    if weberrflag != 0 :
      weberr = weberr + 1

    if weberr > 9 :
      print 'ERROR IN WEB SERVER THREAD, RESTARTING'
      r.terminate()
      sleep(2)
      r.run()
      sleep(2)

    weberrflag = 0

    sleep(1)
