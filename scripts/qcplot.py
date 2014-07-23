import ast
import constants as c
import datetime
import time
import math
import matplotlib.dates as mdt
import matplotlib.pyplot as plt
import meteorologicalfunctions as mf
import numpy
import statsmodels.api as sm
import sys
import qcck
import qcio
import qcutils
import logging

log = logging.getLogger('qc.plot')

def get_diurnalstats(DecHour,Data,dt):
    nInts = 24*int((60/dt)+0.5)
    Hr = numpy.array([-9999]*nInts,dtype=numpy.float64)
    Av = numpy.array([-9999]*nInts,dtype=numpy.float64)
    Sd = numpy.array([-9999]*nInts,dtype=numpy.float64)
    Mx = numpy.array([-9999]*nInts,dtype=numpy.float64)
    Mn = numpy.array([-9999]*nInts,dtype=numpy.float64)
    for i in range(nInts):
        Hr[i] = float(i)*dt/60.
        li = numpy.where((abs(DecHour-Hr[i])<c.eps)&(abs(Data-float(-9999))>c.eps))
        if numpy.size(li)!=0:
            Av[i] = numpy.mean(Data[li])
            Sd[i] = numpy.std(Data[li])
            Mx[i] = numpy.max(Data[li])
            Mn[i] = numpy.min(Data[li])
    return Hr, Av, Sd, Mx, Mn

def get_ticks(start, end):
    from datetime import timedelta as td
    delta = end - start

    if delta <= td(minutes=10):
        loc = mdt.MinuteLocator()
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(minutes=30):
        loc = mdt.MinuteLocator(byminute=range(0,60,5))
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(hours=1):
        loc = mdt.MinuteLocator(byminute=range(0,60,15))
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(hours=6):
        loc = mdt.HourLocator()
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(days=1):
        loc = mdt.HourLocator(byhour=range(0,24,3))
        fmt = mdt.DateFormatter('%H:%M')
    elif delta <= td(days=3):
        loc = mdt.HourLocator(byhour=range(0,24,12))
        fmt = mdt.DateFormatter('%d/%m %H')
    elif delta <= td(weeks=2):
        loc = mdt.DayLocator()
        fmt = mdt.DateFormatter('%d/%m')
    elif delta <= td(weeks=12):
        loc = mdt.WeekdayLocator()
        fmt = mdt.DateFormatter('%d/%m')
    elif delta <= td(weeks=104):
        loc = mdt.MonthLocator()
        fmt = mdt.DateFormatter('%d/%m')
    elif delta <= td(weeks=208):
        loc = mdt.MonthLocator(interval=3)
        fmt = mdt.DateFormatter('%d/%m/%y')
    else:
        loc = mdt.MonthLocator(interval=6)
        fmt = mdt.DateFormatter('%d/%m/%y')
    return loc,fmt

def get_yarray(ds,ThisOne,si=0,ei=-1):
    yarray = numpy.ma.masked_where(abs(ds.series[ThisOne]['Data'][si:ei]-float(-9999))<c.eps,
                                        ds.series[ThisOne]['Data'][si:ei])
    nRecs = numpy.ma.size(yarray)
    nNotM = numpy.ma.count(yarray)
    nMskd = numpy.ma.count_masked(yarray)
    if numpy.ma.count(yarray)==0:
        yarray = numpy.ma.zeros(numpy.size(yarray))
    return yarray,nRecs,nNotM,nMskd
    
def get_yaxislimitsfromcf(cf,nFig,maxkey,minkey,nSer,YArray):
    if maxkey in cf['Plots'][str(nFig)].keys():                               # Y axis minima specified
        maxlist = ast.literal_eval(cf['Plots'][str(nFig)][maxkey])     # Evaluate the minima list
        if str(maxlist[nSer])=='Auto':             # This entry is 'Auto' ...
            YAxMax = numpy.ma.maximum(YArray)                        # ... so take the array minimum value
        else:
            YAxMax = float(maxlist[nSer])         # Evaluate the entry for this series
    else:
        YAxMax = numpy.ma.maximum(YArray)                            # Y axis minima not given, use auto
    if minkey in cf['Plots'][str(nFig)].keys():                               # Y axis minima specified
        minlist = ast.literal_eval(cf['Plots'][str(nFig)][minkey])     # Evaluate the minima list
        if str(minlist[nSer])=='Auto':             # This entry is 'Auto' ...
            YAxMin = numpy.ma.minimum(YArray)                        # ... so take the array minimum value
        else:
            YAxMin = float(minlist[nSer])         # Evaluate the entry for this series
    else:
        YAxMin = numpy.ma.minimum(YArray)                            # Y axis minima not given, use auto
    return YAxMax,YAxMin

def plot_fingerprint(cf):
    """ Do a fingerprint plot"""
    infilename = qcio.get_infilename_from_cf(cf)
    # read the netCDF file and return the data structure "ds"
    ds = qcio.nc_read_series(infilename)
    if len(ds.series.keys())==0:
        log.error("netCDF file "+infilename+" not found")
        return
    # make sure the specific humidity deficit (SHD) is in the data structure
    if "SHD" not in ds.series.keys():
        Ah,f,a = qcutils.GetSeriesasMA(ds,"Ah")
        Ta,f,a = qcutils.GetSeriesasMA(ds,"Ta")
        ps,f,a = qcutils.GetSeriesasMA(ds,"ps")
        e = mf.vapourpressure(Ah,Ta)                  # vapour pressure from absolute humidity and temperature
        esat = mf.es(Ta)                              # saturation vapour pressure
        mr = mf.mixingratio(ps,e)                     # mixing ratio
        mrsat = mf.mixingratio(ps,esat)               # saturation mixing ratio
        q = mf.specifichumidity(mr)                   # specific humidity from mixing ratio
        qsat = mf.specifichumidity(mrsat)             # saturation specific humidity from saturation mixing ratio
        SHD = qsat - q                                # specific humidity deficit
        attr = qcutils.MakeAttributeDictionary(long_name='Specific humidity deficit',units='kg/kg')
        qcutils.CreateSeries(ds,'SHD',SHD,FList=["Ta","Ah","ps"],Attr=attr)
    # get some useful things
    ts = int(ds.globalattributes["time_step"])
    site_name = str(ds.globalattributes['site_name'])
    level = str(ds.globalattributes['nc_level'])
    nRecs = int(ds.globalattributes['nc_nrecs'])
    # check for time gaps in the file
    if qcutils.CheckTimeStep(ds): qcutils.FixTimeGaps(ds)
    # title string for plots
    TitleStr = site_name+' '+level
    # number of records per hour and number per day
    nPerHr = int(float(60)/ts+0.5)
    nPerDay = int(float(24)*nPerHr+0.5)
    # get the datetime series
    DateTime = ds.series['DateTime']['Data']
    StartDate = str(ds.series['DateTime']['Data'][0])
    EndDate = str(ds.series['DateTime']['Data'][-1])
    # find the start index of the first whole day (time=00:30)
    si = qcutils.GetDateIndex(DateTime,StartDate,ts=ts,default=0,match='startnextday')
    # find the end index of the last whole day (time=00:00)
    ei = qcutils.GetDateIndex(DateTime,EndDate,ts=ts,default=-1,match='endpreviousday')
    # truncate the datetie series to whole days
    DateTime = DateTime[si:ei+1]
    sd = datetime.datetime.toordinal(DateTime[0])
    ed = datetime.datetime.toordinal(DateTime[-1])
    TitleStr = TitleStr+' from '+str(DateTime[0])+' to '+str(DateTime[-1])
    nDays = len(DateTime)/nPerDay
    # do the plots
    plt.ion()
    for nFig in cf['Plots'].keys():
        n = 0
        fig = plt.figure(nFig,figsize=[15,10])
        fig.canvas.set_window_title(cf["Plots"][str(nFig)]["Title"])
        plt.figtext(0.5,0.95,TitleStr,horizontalalignment='center')
        SeriesList = qcutils.GetPlotVariableNamesFromCF(cf,nFig)
        nPlots = len(SeriesList)
        for ThisOne in SeriesList:
            n += 1
            VarName = qcutils.GetAltNameFromCF(cf,ThisOne)
            ticks = qcutils.GetcbTicksFromCF(cf,ThisOne)
            data,flag,attr = qcutils.GetSeriesasMA(ds,VarName,si=si,ei=ei)
            lower, upper = qcutils.GetRangesFromCF(cf,ThisOne)
            data = qcck.cliptorange(data, lower, upper)
            data_daily = data.reshape(nDays,nPerDay)
            units = str(ds.series[VarName]['Attr']['units'])
            label = VarName + ' (' + units + ')'
            loc,fmt = get_ticks(datetime.datetime.fromordinal(sd),datetime.datetime.fromordinal(ed))
            ax = plt.subplot(1,nPlots,n)
            plt.imshow(data_daily,extent=[0,24,sd,ed],aspect='auto',origin='lower')
            ax.yaxis.set_major_locator(loc)
            ax.yaxis.set_major_formatter(fmt)
            plt.colorbar(orientation='horizontal',fraction=0.02,pad=0.075,ticks=ticks)
            plt.xticks([0,6,12,18,24])
            plt.xlabel(label)
            if n!= 1: plt.setp(ax.get_yticklabels(), visible=False)
        pngname = 'plots/'+site_name.replace(' ','')+'_'+level+'_'
        pngname = pngname+qcutils.GetPlotTitleFromCF(cf,nFig).replace(' ','_')+'.png'
        fig.savefig(pngname,format='png')
        plt.draw()
    plt.ioff()

def plottimeseries(cf,nFig,dsa,dsb,si,ei):
    SiteName = dsa.globalattributes['site_name']
    Level = dsb.globalattributes['nc_level']
    dt = int(dsa.globalattributes['time_step'])
    Month = dsa.series['Month']['Data'][0]
    p = plot_setup(cf,nFig)
    log.info(' Plotting series: '+str(p['SeriesList']))
    L1XArray = numpy.array(dsa.series['DateTime']['Data'][si:ei])
    L2XArray = numpy.array(dsb.series['DateTime']['Data'][si:ei])
    p['XAxMin'] = min(L2XArray)
    p['XAxMax'] = max(L2XArray)
    p['loc'],p['fmt'] = get_ticks(p['XAxMin'],p['XAxMax'])
    plt.ioff()
    fig = plt.figure(int(nFig),figsize=(p['PlotWidth'],p['PlotHeight']))
    fig.clf()
    plt.figtext(0.5,0.95,SiteName+': '+p['PlotDescription'],ha='center',size=16)
    for ThisOne, n in zip(p['SeriesList'],range(p['nGraphs'])):
        if ThisOne in dsa.series.keys():
            aflag = dsa.series[ThisOne]['Flag']
            p['Units'] = dsa.series[ThisOne]['Attr']['units']
            p['YAxOrg'] = p['ts_YAxOrg'] + n*p['yaxOrgOffset']
            L1YArray,p['nRecs'],p['nNotM'],p['nMskd'] = get_yarray(dsa,ThisOne,si=si,ei=ei)
            # check the control file to see if the Y axis minima have been specified
            nSer = p['SeriesList'].index(ThisOne)
            p['LYAxMax'],p['LYAxMin'] = get_yaxislimitsfromcf(cf,nFig,'YLMax','YLMin',nSer,L1YArray)
            plot_onetimeseries_left(fig,n,ThisOne,L1XArray,L1YArray,p)
        if ThisOne in dsb.series.keys():
            bflag = dsb.series[ThisOne]['Flag']
            p['Units'] = dsb.series[ThisOne]['Attr']['units']
            p['YAxOrg'] = p['ts_YAxOrg'] + n*p['yaxOrgOffset']
            #Plot the Level 2 data series on the same X axis but with the scale on the right Y axis.
            L2YArray,p['nRecs'],p['nNotM'],p['nMskd'] = get_yarray(dsb,ThisOne,si=si,ei=ei)
            # check the control file to see if the Y axis minima have been specified
            nSer = p['SeriesList'].index(ThisOne)
            p['RYAxMax'],p['RYAxMin'] = get_yaxislimitsfromcf(cf,nFig,'YRMax','YRMin',nSer,L2YArray)
            plot_onetimeseries_right(fig,n,ThisOne,L2XArray,L2YArray,p)

            #Plot the diurnal averages.
            Hr2,Av2,Sd2,Mx2,Mn2=get_diurnalstats(dsb.series['Hdh']['Data'][si:ei],
                                                dsb.series[ThisOne]['Data'][si:ei],dt)
            Av2 = numpy.ma.masked_where(Av2==-9999,Av2)
            Sd2 = numpy.ma.masked_where(Sd2==-9999,Sd2)
            Mx2 = numpy.ma.masked_where(Mx2==-9999,Mx2)
            Mn2 = numpy.ma.masked_where(Mn2==-9999,Mn2)
            hr2_ax = fig.add_axes([p['hr1_XAxOrg'],p['YAxOrg'],p['hr2_XAxLen'],p['ts_YAxLen']])
            hr2_ax.hold(True)
            hr2_ax.plot(Hr2,Av2,'y-',Hr2,Mx2,'r-',Hr2,Mn2,'b-')
            section = qcutils.get_cfsection(cf,series=ThisOne,mode='quiet')
            if len(section)!=0:
                if 'DiurnalCheck' in cf[section][ThisOne].keys():
                    NSdarr = numpy.array(eval(cf[section][ThisOne]['DiurnalCheck']['NumSd']),dtype=float)
                    nSd = NSdarr[Month-1]
                    hr2_ax.plot(Hr2,Av2+nSd*Sd2,'r.',Hr2,Av2-nSd*Sd2,'b.')
            plt.xlim(0,24)
            plt.xticks([0,6,12,18,24])
            if n==0:
                hr2_ax.set_xlabel('Hour',visible=True)
            else:
                hr2_ax.set_xlabel('',visible=False)
                plt.setp(hr2_ax.get_xticklabels(), visible=False)
            #if n > 0: plt.setp(hr2_ax.get_xticklabels(), visible=False)

            # vertical lines to show frequency distribution of flags
            bins = numpy.arange(0.5,23.5)
            ind = bins[:len(bins)-1]+0.5
            index = numpy.where(numpy.mod(bflag,10)==0)    # find the elements with flag = 0, 10, 20 etc
            bflag[index] = 0                               # set them all to 0
            hist, bin_edges = numpy.histogram(bflag, bins=bins)
            ymin = hist*0
            delta = 0.01*(numpy.max(hist)-numpy.min(hist))
            bar_ax = fig.add_axes([p['hr2_XAxOrg'],p['YAxOrg'],p['bar_XAxLen'],p['ts_YAxLen']])
            bar_ax.set_ylim(0,numpy.max(hist))
            bar_ax.vlines(ind,ymin,hist)
            for i,j in zip(ind,hist):
                if j>0.05*numpy.max(hist): bar_ax.text(i,j+delta,str(int(i)),ha='center',size='small')
            if n==0:
                bar_ax.set_xlabel('Flag',visible=True)
            else:
                bar_ax.set_xlabel('',visible=False)
                plt.setp(bar_ax.get_xticklabels(), visible=False)
            #if n > 0: plt.setp(bar_ax.get_xticklabels(), visible=False)
        else:
            log.error('  plttimeseries: series '+ThisOne+' not in data structure')
    fig.show()
    fname = 'plots/'+SiteName.replace(' ','')+'_'+Level+'_'+p['PlotDescription'].replace(' ','')+'.png'
    fig.savefig(fname,format='png')

def plot_quickcheck(cf):
    nFig = 0
    # get the netCDF filename
    ncfilename = qcio.get_infilename_from_cf(cf)
    # get the plot width and height
    PlotWidth_landscape = float(cf['General']['PlotWidth_landscape'])
    PlotHeight_landscape = float(cf['General']['PlotHeight_landscape'])
    PlotWidth_portrait = float(cf['General']['PlotWidth_portrait'])
    PlotHeight_portrait = float(cf['General']['PlotHeight_portrait'])
    # read the netCDF file and return the data structure "ds"
    log.info(' Opening and reading netCDF file '+ncfilename)
    ds = qcio.nc_read_series(ncfilename)
    if len(ds.series.keys())==0: log.error(' netCDF file '+ncfilename+' not found'); sys.exit()
    # get the time step
    ts = int(ds.globalattributes['time_step'])
    # get the site name
    SiteName = ds.globalattributes['site_name']
    # get the datetime series
    DateTime = ds.series['DateTime']['Data']
    # get the initial start and end dates
    StartDate = str(DateTime[0])
    EndDate = str(DateTime[-1])
    # find the start index of the first whole day (time=00:30)
    si = qcutils.GetDateIndex(DateTime,StartDate,ts=ts,default=0,match='startnextday')
    # find the end index of the last whole day (time=00:00)
    ei = qcutils.GetDateIndex(DateTime,EndDate,ts=ts,default=-1,match='endpreviousday')
    DateTime = DateTime[si:ei+1]
    PlotTitle = SiteName + ': ' + str(DateTime[0]) + ' to ' + str(DateTime[-1])
    # get the final start and end dates
    StartDate = str(DateTime[0])
    EndDate = str(DateTime[-1])
    # get the 30 minute data from the data structure
    log.info(' Getting data from data structure ')
    #  radiation first ...
    Mnth_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Month'),si=si,ei=ei)
    Hour_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Hour'),si=si,ei=ei)
    Mnit_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Minute'),si=si,ei=ei)
    Fsd,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fsd'),si=si,ei=ei)
    if 'Fsd_syn' in ds.series.keys():
        Fsd_syn,flag,attr = qcutils.GetSeriesasMA(ds,'Fsd_syn',si=si,ei=ei)
        index = numpy.ma.where(Fsd.mask==True)[0]
        Fsd[index] = Fsd_syn[index]
    night_mask = (Fsd<10)
    day_mask = (Fsd>=10)
    Fsd_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fsd'),si=si,ei=ei)
    Fsu_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fsu'),si=si,ei=ei)
    Fld_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fld'),si=si,ei=ei)
    Flu_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Flu'),si=si,ei=ei)
    Fn_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fn'),si=si,ei=ei)
    #  then fluxes ...
    Fg_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fg'),si=si,ei=ei)
    Fa2_30min = Fn_30min - Fg_30min
    Fa_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fa'),si=si,ei=ei)
    index = numpy.where((Fa_30min.mask==True)&(Fa2_30min.mask==False))[0]
    Fa_30min[index] = Fa2_30min[index]
    Fe_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fe'),si=si,ei=ei)
    Fh_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fh'),si=si,ei=ei)
    Fc_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Fc'),si=si,ei=ei)
    Fc_units = ds.series[qcutils.GetAltName(cf,ds,'Fc')]['Attr']['units']
    us_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'ustar'),si=si,ei=ei)
    #  then meteorology ...
    Ta_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Ta'),si=si,ei=ei)
    H2O_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'H2O'),si=si,ei=ei)
    H2O_units = ds.series[qcutils.GetAltName(cf,ds,'H2O')]['Attr']['units']
    CO2_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'CO2'),si=si,ei=ei)
    CO2_units = ds.series[qcutils.GetAltName(cf,ds,'CO2')]['Attr']['units']
    Rain_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Precip'),si=si,ei=ei)
    Ws_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Ws'),si=si,ei=ei)
    #  then soil ...
    Sws_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Sws'),si=si,ei=ei)
    Ts_30min,flag,attr = qcutils.GetSeriesasMA(ds,qcutils.GetAltName(cf,ds,'Ts'),si=si,ei=ei)
    
    # get the number of days in the data set
    ntsInDay = float(24.0*60.0/float(ts))
    if math.modf(ntsInDay)[0]!=0:
        print 'quickcheck: Time step is not a sub-multiple of 60 minutes ', ts
        sys.exit
    ntsInDay = int(ntsInDay)
    nDays = float(len(DateTime))/ntsInDay
    if math.modf(nDays)[0]!=0:
        print 'quickcheck: Not a whole number of days ', nDays
        sys.exit
    nDays = int(nDays)
    
    # *** start of section based on 30 minute data ***
    # scatter plot of (Fh+Fe) versys Fa, all data
    log.info(' Doing surface energy balance plots ')
    mask = numpy.ma.mask_or(Fa_30min.mask,Fe_30min.mask)
    mask = numpy.ma.mask_or(mask,Fh_30min.mask)
    Fa_SEB = numpy.ma.array(Fa_30min,mask=mask)     # apply the mask
    FhpFe_SEB = numpy.ma.array(Fh_30min,mask=mask) + numpy.ma.array(Fe_30min,mask=mask)
    nFig = nFig + 1
    plt.ion()
    fig = plt.figure(nFig,figsize=(8,8))
    fig.canvas.set_window_title("Surface Energy Balance")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    xyplot(Fa_SEB,FhpFe_SEB,sub=[2,2,1],regr=1,title="All hours",xlabel='Fa (W/m2)',ylabel='Fh+Fe (W/m2)')
    # scatter plot of (Fh+Fe) versus Fa, 24 hour averages
    Fa_daily = Fa_30min.reshape(nDays,ntsInDay)
    Fe_daily = Fe_30min.reshape(nDays,ntsInDay)
    Fh_daily = Fh_30min.reshape(nDays,ntsInDay)
    mask = numpy.ma.mask_or(Fa_daily.mask,Fe_daily.mask)
    mask = numpy.ma.mask_or(mask,Fh_daily.mask)
    Fa_daily = numpy.ma.array(Fa_daily,mask=mask)         # apply the mask
    Fe_daily = numpy.ma.array(Fe_daily,mask=mask)
    Fh_daily = numpy.ma.array(Fh_daily,mask=mask)
    Fa_daily_avg = numpy.ma.average(Fa_daily,axis=1)      # get the daily average
    Fe_daily_avg = numpy.ma.average(Fe_daily,axis=1)
    Fh_daily_avg = numpy.ma.average(Fh_daily,axis=1)
    FhpFe_daily_avg = Fh_daily_avg + Fe_daily_avg
    xyplot(Fa_daily_avg,FhpFe_daily_avg,sub=[2,2,2],regr=1,thru0=1,title="Daily Average",xlabel='Fa (W/m2)',ylabel='Fh+Fe (W/m2)')
    # scatter plot of (Fh+Fe) versus Fa, day time
    Fa_day = numpy.ma.masked_where(day_mask==False,Fa_30min)
    Fe_day = numpy.ma.masked_where(day_mask==False,Fe_30min)
    Fh_day = numpy.ma.masked_where(day_mask==False,Fh_30min)
    mask = numpy.ma.mask_or(Fa_day.mask,Fe_day.mask)
    mask = numpy.ma.mask_or(mask,Fh_day.mask)
    Fa_day = numpy.ma.array(Fa_day,mask=mask)         # apply the mask
    Fe_day = numpy.ma.array(Fe_day,mask=mask)
    Fh_day = numpy.ma.array(Fh_day,mask=mask)
    FhpFe_day = Fh_day + Fe_day
    xyplot(Fa_day,FhpFe_day,sub=[2,2,3],regr=1,title="Day",xlabel='Fa (W/m2)',ylabel='Fh+Fe (W/m2)')
    # scatter plot of (Fh+Fe) versus Fa, night time
    Fa_night = numpy.ma.masked_where(night_mask==False,Fa_30min)
    Fe_night = numpy.ma.masked_where(night_mask==False,Fe_30min)
    Fh_night = numpy.ma.masked_where(night_mask==False,Fh_30min)
    mask = numpy.ma.mask_or(Fa_night.mask,Fe_night.mask)
    mask = numpy.ma.mask_or(mask,Fh_night.mask)
    Fa_night = numpy.ma.array(Fa_night,mask=mask)         # apply the mask
    Fe_night = numpy.ma.array(Fe_night,mask=mask)
    Fh_night = numpy.ma.array(Fh_night,mask=mask)
    FhpFe_night = Fh_night + Fe_night
    xyplot(Fa_night,FhpFe_night,sub=[2,2,4],regr=1,title="Night",xlabel='Fa (W/m2)',ylabel='Fh+Fe (W/m2)')
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'SEB_30minutes.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # *** start of section based on daily averages ***
    log.info(' Getting daily averages from 30 minute data ')
    MTFmt = mdt.DateFormatter('%m/%Y')
    # reshape the 1D array of 30 minute data into a 2D array of (nDays,ntsInDay)
    DT_daily = DateTime[0::ntsInDay]
    Mnth_daily = Mnth_30min.reshape(nDays,ntsInDay)
    Hour_daily = Hour_30min.reshape(nDays,ntsInDay)
    Mnit_daily = Mnit_30min.reshape(nDays,ntsInDay)
    dm_daily = day_mask.reshape(nDays,ntsInDay)
    nm_daily = night_mask.reshape(nDays,ntsInDay)
    Fn_daily = Fn_30min.reshape(nDays,ntsInDay)
    Fa_daily = Fa_30min.reshape(nDays,ntsInDay)
    Fe_daily = Fe_30min.reshape(nDays,ntsInDay)
    Fh_daily = Fh_30min.reshape(nDays,ntsInDay)
    Fc_daily = Fc_30min.reshape(nDays,ntsInDay)
    Rain_daily = Rain_30min.reshape(nDays,ntsInDay)
    Sws_daily = Sws_30min.reshape(nDays,ntsInDay)
    Ts_daily = Ts_30min.reshape(nDays,ntsInDay)
    us_daily = us_30min.reshape(nDays,ntsInDay)
    
    # get the SEB ratio
    # get the daytime data, defined by Fsd>10 W/m2
    Fa_day = numpy.ma.masked_where(nm_daily==True,Fa_daily)
    Fe_day = numpy.ma.masked_where(nm_daily==True,Fe_daily)
    Fh_day = numpy.ma.masked_where(nm_daily==True,Fh_daily)
    mask = numpy.ma.mask_or(Fa_day.mask,Fe_day.mask)  # mask based on dependencies, set all to missing if any missing
    mask = numpy.ma.mask_or(mask,Fh_day.mask)
    Fa_day = numpy.ma.array(Fa_day,mask=mask)         # apply the mask
    Fe_day = numpy.ma.array(Fe_day,mask=mask)
    Fh_day = numpy.ma.array(Fh_day,mask=mask)
    Fa_day_avg = numpy.ma.average(Fa_day,axis=1)      # get the daily average
    Fe_day_avg = numpy.ma.average(Fe_day,axis=1)
    Fh_day_avg = numpy.ma.average(Fh_day,axis=1)      # get the number of values in the daily average
    SEB_day_num = numpy.ma.count(Fh_day,axis=1)       # get the SEB ratio
    SEB_day_avg = (Fe_day_avg+Fh_day_avg)/Fa_day_avg
    SEB_day_avg = numpy.ma.masked_where(SEB_day_num<=5,SEB_day_avg)
    index = numpy.ma.where(SEB_day_avg.mask==True)
    SEB_day_num[index] = 0
    
    # get the EF
    # get the daytime data, defined by Fsd>10 W/m2
    Fa_day = numpy.ma.masked_where(nm_daily==True,Fa_daily)
    Fe_day = numpy.ma.masked_where(nm_daily==True,Fe_daily)
    mask = numpy.ma.mask_or(Fa_day.mask,Fe_day.mask)  # mask based on dependencies, set all to missing if any missing
    Fa_day = numpy.ma.array(Fa_day,mask=mask)         # apply the mask
    Fe_day = numpy.ma.array(Fe_day,mask=mask)
    Fa_day_avg = numpy.ma.average(Fa_day,axis=1)      # get the daily average
    Fe_day_avg = numpy.ma.average(Fe_day,axis=1)
    EF_day_num = numpy.ma.count(Fe_day,axis=1)        # get the number of values in the daily average
    EF_day_avg = Fe_day_avg/Fa_day_avg                # get the EF ratio
    EF_day_avg = numpy.ma.masked_where(EF_day_num<=5,EF_day_avg)
    index = numpy.ma.where(EF_day_avg.mask==True)
    EF_day_num[index] = 0
    
    # get the BR
    # get the daytime data, defined by Fsd>10 W/m2
    Fe_day = numpy.ma.masked_where(nm_daily==True,Fe_daily)
    Fh_day = numpy.ma.masked_where(nm_daily==True,Fh_daily)
    mask = numpy.ma.mask_or(Fe_day.mask,Fh_day.mask)  # mask based on dependencies, set all to missing if any missing
    Fe_day = numpy.ma.array(Fe_day,mask=mask)         # apply the mask
    Fh_day = numpy.ma.array(Fh_day,mask=mask)
    Fe_day_avg = numpy.ma.average(Fe_day,axis=1)      # get the daily average
    Fh_day_avg = numpy.ma.average(Fh_day,axis=1)
    BR_day_num = numpy.ma.count(Fh_day,axis=1)        # get the number of values in the daily average
    BR_day_avg = Fh_day_avg/Fe_day_avg                # get the BR ratio
    BR_day_avg = numpy.ma.masked_where(BR_day_num<=5,BR_day_avg)
    index = numpy.ma.where(BR_day_avg.mask==True)
    BR_day_num[index] = 0
    
    # get the Wue
    # get the daytime data, defined by Fsd>10 W/m2
    Fe_day = numpy.ma.masked_where(nm_daily==True,Fe_daily)
    Fc_day = numpy.ma.masked_where(nm_daily==True,Fc_daily)
    mask = numpy.ma.mask_or(Fe_day.mask,Fc_day.mask)  # mask based on dependencies, set all to missing if any missing
    Fe_day = numpy.ma.array(Fe_day,mask=mask)         # apply the mask
    Fc_day = numpy.ma.array(Fc_day,mask=mask)
    Fe_day_avg = numpy.ma.average(Fe_day,axis=1)      # get the daily average
    Fc_day_avg = numpy.ma.average(Fc_day,axis=1)
    WUE_day_num = numpy.ma.count(Fc_day,axis=1)       # get the number of values in the daily average
    WUE_day_avg = Fc_day_avg/Fe_day_avg
    WUE_day_avg = numpy.ma.masked_where(WUE_day_num<=5,WUE_day_avg)
    index = numpy.ma.where(WUE_day_avg.mask==True)
    WUE_day_num[index] = 0
    # get the soil moisture
    Sws_daily_avg = numpy.ma.average(Sws_daily,axis=1)
    Sws_daily_num = numpy.ma.count(Sws_daily,axis=1)
    # get the rainfall
    Rain_daily_sum = numpy.ma.sum(Rain_daily,axis=1)
    Rain_daily_num = numpy.ma.count(Rain_daily,axis=1)
    # plot the SEB, EF and Wue
    log.info(' Doing the daily ratios plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_landscape,PlotHeight_landscape))
    fig.canvas.set_window_title("Daily Average Ratios")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    tsplot(DT_daily,SEB_day_avg,sub=[6,1,1],colours=SEB_day_num,ylabel='(Fh+Fe)/Fa',lineat=1)
    tsplot(DT_daily,EF_day_avg,sub=[6,1,2],colours=EF_day_num,ylabel='EF=Fe/Fa')
    tsplot(DT_daily,BR_day_avg,sub=[6,1,3],colours=BR_day_num,ylabel='BR=Fh/Fe')
    tsplot(DT_daily,WUE_day_avg,sub=[6,1,4],colours=WUE_day_num,ylabel='WUE=Fc/Fe',lineat=0)
    tsplot(DT_daily,Sws_daily_avg,sub=[6,1,5],colours=Sws_daily_num,ylabel='Sws')
    tsplot(DT_daily,Rain_daily_sum,sub=[6,1,6],colours=Rain_daily_num,ylabel='Rain')
    #fig.show()
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DailyRatios.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # now we do the daily averages of the fluxes and the meteorology
    # get the 1D array of 30 minute data into a 2D array with a dimension for
    #  the day number and a dimension for the time of day
    Fsd_daily = Fsd_30min.reshape(nDays,ntsInDay)
    Fsu_daily = Fsu_30min.reshape(nDays,ntsInDay)
    Fld_daily = Fld_30min.reshape(nDays,ntsInDay)
    Flu_daily = Flu_30min.reshape(nDays,ntsInDay)
    Fn_daily = Fn_30min.reshape(nDays,ntsInDay)
    Fg_daily = Fg_30min.reshape(nDays,ntsInDay)
    Fsd_day = numpy.ma.masked_where(nm_daily==True,Fsd_daily)
    Fsu_day = numpy.ma.masked_where(nm_daily==True,Fsu_daily)
    Fld_day = numpy.ma.masked_where(nm_daily==True,Fld_daily)
    Flu_day = numpy.ma.masked_where(nm_daily==True,Flu_daily)
    Fn_day = numpy.ma.masked_where(nm_daily==True,Fn_daily)
    Fg_day = numpy.ma.masked_where(nm_daily==True,Fg_daily)
    Fsd_day_avg = numpy.ma.average(Fsd_day,axis=1)
    Fsu_day_avg = numpy.ma.average(Fsu_day,axis=1)
    Fld_day_avg = numpy.ma.average(Fld_day,axis=1)
    Flu_day_avg = numpy.ma.average(Flu_day,axis=1)
    Fn_day_avg = numpy.ma.average(Fn_day,axis=1)
    Fg_day_avg = numpy.ma.average(Fg_day,axis=1)
    Fsd_day_num = numpy.ma.count(Fsd_day,axis=1)
    Fsu_day_num = numpy.ma.count(Fsu_day,axis=1)
    Fld_day_num = numpy.ma.count(Fld_day,axis=1)
    Flu_day_num = numpy.ma.count(Flu_day,axis=1)
    Fn_day_num = numpy.ma.count(Fn_day,axis=1)
    Fg_day_num = numpy.ma.count(Fg_day,axis=1)
    log.info(' Doing the daily radiation plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_landscape,PlotHeight_landscape))
    fig.canvas.set_window_title("Daily Average Radiation")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    tsplot(DT_daily,Fsd_day_avg,sub=[6,1,1],colours=Fsd_day_num,ylabel='Fsd (W/m2)')
    tsplot(DT_daily,Fsu_day_avg,sub=[6,1,2],colours=Fsu_day_num,ylabel='Fsu (W/m2)')
    tsplot(DT_daily,Fld_day_avg,sub=[6,1,3],colours=Fld_day_num,ylabel='Fld (W/m2)')
    tsplot(DT_daily,Flu_day_avg,sub=[6,1,4],colours=Flu_day_num,ylabel='Flu (W/m2)')
    tsplot(DT_daily,Fn_day_avg,sub=[6,1,5],colours=Fn_day_num,ylabel='Fn (W/m2)')
    tsplot(DT_daily,Fg_day_avg,sub=[6,1,6],colours=Fg_day_num,ylabel='Fg (W/m2)')
    #fig.show()
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DailyRadn.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    Fsd_daily = Fsd_30min.reshape(nDays,ntsInDay)
    Fa_daily = Fa_30min.reshape(nDays,ntsInDay)
    Fe_daily = Fe_30min.reshape(nDays,ntsInDay)
    Fh_daily = Fh_30min.reshape(nDays,ntsInDay)
    Fc_daily = Fc_30min.reshape(nDays,ntsInDay)
    # ... then get the day time values only (defined by Fsd>10 W/m2)
    Fsd_day = numpy.ma.masked_where(nm_daily==True,Fsd_daily)
    Fa_day = numpy.ma.masked_where(nm_daily==True,Fa_daily)
    Fe_day = numpy.ma.masked_where(nm_daily==True,Fe_daily)
    Fh_day = numpy.ma.masked_where(nm_daily==True,Fh_daily)
    Fc_day = numpy.ma.masked_where(nm_daily==True,Fc_daily)
    Fc_night = numpy.ma.masked_where(nm_daily==True,Fc_daily)
    # ... then get the daily averages
    Fsd_day_avg = numpy.ma.average(Fsd_day,axis=1)      # get the daily average
    Fa_day_avg = numpy.ma.average(Fa_day,axis=1)      # get the daily average
    Fe_day_avg = numpy.ma.average(Fe_day,axis=1)      # get the daily average
    Fh_day_avg = numpy.ma.average(Fh_day,axis=1)      # get the daily average
    Fc_day_avg = numpy.ma.average(Fc_day,axis=1)      # get the daily average
    Fc_night_avg = numpy.ma.average(Fc_night,axis=1)      # get the daily average
    # ... then the number of values in each day time block
    Fsd_day_num = numpy.ma.count(Fsd_day,axis=1)
    Fa_day_num = numpy.ma.count(Fa_day,axis=1)
    Fe_day_num = numpy.ma.count(Fe_day,axis=1)
    Fh_day_num = numpy.ma.count(Fh_day,axis=1)
    Fc_day_num = numpy.ma.count(Fc_day,axis=1)
    Fc_night_num = numpy.ma.count(Fc_night,axis=1)
    # ... now plot the day time averages with the colour of the points controlled
    #     by the number of values used to get the average
    log.info(' Doing the daily fluxes plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_landscape,PlotHeight_landscape))
    fig.canvas.set_window_title("Daily Average Fluxes")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    tsplot(DT_daily,Fsd_day_avg,sub=[5,1,1],colours=Fsd_day_num,ylabel='Fsd (W/m2)')
    tsplot(DT_daily,Fa_day_avg,sub=[5,1,2],colours=Fa_day_num,ylabel='Fa (W/m2)')
    tsplot(DT_daily,Fe_day_avg,sub=[5,1,3],colours=Fe_day_num,ylabel='Fe (W/m2)')
    tsplot(DT_daily,Fh_day_avg,sub=[5,1,4],colours=Fh_day_num,ylabel='Fh (W/m2)')
    tsplot(DT_daily,Fc_day_avg,sub=[5,1,5],colours=Fc_day_num,ylabel='Fc ('+Fc_units+')',lineat=0)
    #fig.show()
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DailyFluxes.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    Ta_daily = Ta_30min.reshape(nDays,ntsInDay)
    H2O_daily = H2O_30min.reshape(nDays,ntsInDay)
    CO2_daily = CO2_30min.reshape(nDays,ntsInDay)
    Ws_daily = Ws_30min.reshape(nDays,ntsInDay)
    CO2_day = numpy.ma.masked_where(nm_daily==True,CO2_daily)
    Ta_daily_avg = numpy.ma.average(Ta_daily,axis=1)      # get the daily average
    Ta_daily_num = numpy.ma.count(Ta_daily,axis=1)
    H2O_daily_avg = numpy.ma.average(H2O_daily,axis=1)      # get the daily average
    H2O_daily_num = numpy.ma.count(H2O_daily,axis=1)
    CO2_day_avg = numpy.ma.average(CO2_day,axis=1)          # get the daily average
    CO2_day_num = numpy.ma.count(CO2_day,axis=1)
    Ws_daily_avg = numpy.ma.average(Ws_daily,axis=1)      # get the daily average
    Ws_daily_num = numpy.ma.count(Ws_daily,axis=1)
    log.info(' Doing the daily meteorology plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_landscape,PlotHeight_landscape))
    fig.canvas.set_window_title("Daily Average Meteorology")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    tsplot(DT_daily,Ta_daily_avg,sub=[5,1,1],colours=Ta_daily_num,ylabel='Ta (C)')
    tsplot(DT_daily,H2O_daily_avg,sub=[5,1,2],colours=H2O_daily_num,ylabel='H2O ('+H2O_units+')')
    tsplot(DT_daily,CO2_day_avg,sub=[5,1,3],colours=CO2_day_num,ylabel='CO2 ('+CO2_units+')')
    tsplot(DT_daily,Ws_daily_avg,sub=[5,1,4],colours=Ws_daily_num,ylabel='WS (m/s)')
    tsplot(DT_daily,Rain_daily_sum,sub=[5,1,5],colours=Rain_daily_num,ylabel='Rain (mm)')
    #fig.show()
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DailyMet.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    Ta_daily = Ta_30min.reshape(nDays,ntsInDay)
    Ts_daily = Ts_30min.reshape(nDays,ntsInDay)
    Sws_daily = Sws_30min.reshape(nDays,ntsInDay)
    Fg_daily = Fg_30min.reshape(nDays,ntsInDay)
    Rain_daily = Rain_30min.reshape(nDays,ntsInDay)
    Ta_daily_avg = numpy.ma.average(Ta_daily,axis=1)      # get the daily average
    Ta_daily_num = numpy.ma.count(Ta_daily,axis=1)
    Ts_daily_avg = numpy.ma.average(Ts_daily,axis=1)      # get the daily average
    Ts_daily_num = numpy.ma.count(Ts_daily,axis=1)
    Sws_day_avg = numpy.ma.average(Sws_daily,axis=1)          # get the daily average
    Sws_day_num = numpy.ma.count(Sws_daily,axis=1)
    Fg_daily_avg = numpy.ma.average(Fg_daily,axis=1)      # get the daily average
    Fg_daily_num = numpy.ma.count(Fg_daily,axis=1)
    Fg_daily_avg = numpy.ma.average(Fg_daily,axis=1)      # get the daily average
    Rain_daily_sum = numpy.ma.sum(Rain_daily,axis=1)
    Rain_daily_num = numpy.ma.count(Rain_daily,axis=1)
    log.info(' Doing the daily soil data plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_landscape,PlotHeight_landscape))
    fig.canvas.set_window_title("Daily Average Soil")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    tsplot(DT_daily,Ta_daily_avg,sub=[5,1,1],colours=Ta_daily_num,ylabel='Ta (C)')
    tsplot(DT_daily,Ts_daily_avg,sub=[5,1,2],colours=Ts_daily_num,ylabel='Ts (C)')
    tsplot(DT_daily,Sws_day_avg,sub=[5,1,3],colours=Sws_day_num,ylabel='Sws (frac)')
    tsplot(DT_daily,Fg_daily_avg,sub=[5,1,4],colours=Fg_daily_num,ylabel='Fg (W/m2)')
    tsplot(DT_daily,Rain_daily_sum,sub=[5,1,5],colours=Rain_daily_num,ylabel='Rain (mm)')
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DailySoil.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # *** end of section for time series of daily averages
    # *** start of section for diurnal plots by month ***
    MnthList = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    # plot Fsd
    log.info(' Doing the diurnal Fsd by month plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_portrait,PlotHeight_portrait))
    fig.canvas.set_window_title("Diurnal Fsd")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    j = 0
    for i in [12,1,2,3,4,5,6,7,8,9,10,11]:
        j = j + 1
        index = numpy.where(Mnth_daily==i)[0]
        if len(index)!=0:
            hr = Hour_daily[index]+Mnit_daily[index]/float(60)
            Fsd_hr_avg = numpy.ma.average(Fsd_daily[index],axis=0)
            Fsd_hr_num = numpy.ma.count(Fsd_daily[index],axis=0)
            if j in [1,2,3,4,5,6,7,8,9]:
                xlabel = None
            else:
                xlabel = 'Hour'
            if j in [2,3,5,6,8,9,11,12]:
                ylabel = None
            else:
                ylabel = 'Fsd (W/m2)'
            hrplot(hr[0],Fsd_hr_avg,sub=[4,3,j],
                   title=MnthList[i-1],xlabel=xlabel,ylabel=ylabel,
                   colours=Fsd_hr_num)
    # save the plot to file
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DiurnalFsdByMonth.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # plot Fa
    log.info(' Doing the diurnal Fa by month plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_portrait,PlotHeight_portrait))
    fig.canvas.set_window_title("Diurnal Fa")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    j = 0
    for i in [12,1,2,3,4,5,6,7,8,9,10,11]:
        j = j + 1
        index = numpy.where(Mnth_daily==i)[0]
        if len(index)!=0:
            hr = Hour_daily[index]+Mnit_daily[index]/float(60)
            Fa_hr_avg = numpy.ma.average(Fa_daily[index],axis=0)
            Fa_hr_num = numpy.ma.count(Fa_daily[index],axis=0)
            if j in [1,2,3,4,5,6,7,8,9]:
                xlabel = None
            else:
                xlabel = 'Hour'
            if j in [2,3,5,6,8,9,11,12]:
                ylabel = None
            else:
                ylabel = 'Fa (W/m2)'
            hrplot(hr[0],Fa_hr_avg,sub=[4,3,j],
                   title=MnthList[i-1],xlabel=xlabel,ylabel=ylabel,
                   colours=Fa_hr_num)
    # save the plot to file
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DiurnalFaByMonth.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # plot Fn
    log.info(' Doing the diurnal Fn by month plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_portrait,PlotHeight_portrait))
    fig.canvas.set_window_title("Diurnal Fn")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    j = 0
    for i in [12,1,2,3,4,5,6,7,8,9,10,11]:
        j = j + 1
        index = numpy.where(Mnth_daily==i)[0]
        if len(index)!=0:
            hr = Hour_daily[index]+Mnit_daily[index]/float(60)
            Fn_hr_avg = numpy.ma.average(Fn_daily[index],axis=0)
            Fn_hr_num = numpy.ma.count(Fn_daily[index],axis=0)
            if j in [1,2,3,4,5,6,7,8,9]:
                xlabel = None
            else:
                xlabel = 'Hour'
            if j in [2,3,5,6,8,9,11,12]:
                ylabel = None
            else:
                ylabel = 'Fn (W/m2)'
            hrplot(hr[0],Fn_hr_avg,sub=[4,3,j],
                   title=MnthList[i-1],xlabel=xlabel,ylabel=ylabel,
                   colours=Fn_hr_num)
    # save the plot to file
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DiurnalFnByMonth.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # plot Fg
    log.info(' Doing the diurnal Fg by month plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_portrait,PlotHeight_portrait))
    fig.canvas.set_window_title("Diurnal Fg")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    j = 0
    for i in [12,1,2,3,4,5,6,7,8,9,10,11]:
        j = j + 1
        index = numpy.where(Mnth_daily==i)[0]
        if len(index)!=0:
            hr = Hour_daily[index]+Mnit_daily[index]/float(60)
            Fg_hr_avg = numpy.ma.average(Fg_daily[index],axis=0)
            Fg_hr_num = numpy.ma.count(Fg_daily[index],axis=0)
            if j in [1,2,3,4,5,6,7,8,9]:
                xlabel = None
            else:
                xlabel = 'Hour'
            if j in [2,3,5,6,8,9,11,12]:
                ylabel = None
            else:
                ylabel = 'Fg (W/m2)'
            hrplot(hr[0],Fg_hr_avg,sub=[4,3,j],
                   title=MnthList[i-1],xlabel=xlabel,ylabel=ylabel,
                   colours=Fg_hr_num)
    # save the plot to file
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DiurnalFgByMonth.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # plot Ts
    log.info(' Doing the diurnal Ts by month plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_portrait,PlotHeight_portrait))
    fig.canvas.set_window_title("Diurnal Ts")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    j = 0
    for i in [12,1,2,3,4,5,6,7,8,9,10,11]:
        j = j + 1
        index = numpy.where(Mnth_daily==i)[0]
        if len(index)!=0:
            hr = Hour_daily[index]+Mnit_daily[index]/float(60)
            Ts_hr_avg = numpy.ma.average(Ts_daily[index],axis=0)
            Ts_hr_num = numpy.ma.count(Ts_daily[index],axis=0)
            if j in [1,2,3,4,5,6,7,8,9]:
                xlabel = None
            else:
                xlabel = 'Hour'
            if j in [2,3,5,6,8,9,11,12]:
                ylabel = None
            else:
                ylabel = 'Ts (C)'
            hrplot(hr[0],Ts_hr_avg,sub=[4,3,j],
                   title=MnthList[i-1],xlabel=xlabel,ylabel=ylabel,
                   colours=Fg_hr_num)
    # save the plot to file
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DiurnalTsByMonth.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # plot Fh
    log.info(' Doing the diurnal Fh by month plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_portrait,PlotHeight_portrait))
    fig.canvas.set_window_title("Diurnal Fh")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    j = 0
    for i in [12,1,2,3,4,5,6,7,8,9,10,11]:
        j = j + 1
        index = numpy.where(Mnth_daily==i)[0]
        if len(index)!=0:
            hr = Hour_daily[index]+Mnit_daily[index]/float(60)
            Fh_hr_avg = numpy.ma.average(Fh_daily[index],axis=0)
            Fh_hr_num = numpy.ma.count(Fh_daily[index],axis=0)
            if j in [1,2,3,4,5,6,7,8,9]:
                xlabel = None
            else:
                xlabel = 'Hour'
            if j in [2,3,5,6,8,9,11,12]:
                ylabel = None
            else:
                ylabel = 'Fh (W/m2)'
            hrplot(hr[0],Fh_hr_avg,sub=[4,3,j],
                   title=MnthList[i-1],xlabel=xlabel,ylabel=ylabel,
                   colours=Fh_hr_num)
    # save the plot to file
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DiurnalFhByMonth.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # plot Fe
    log.info(' Doing the diurnal Fe by month plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_portrait,PlotHeight_portrait))
    fig.canvas.set_window_title("Diurnal Fe")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    j = 0
    for i in [12,1,2,3,4,5,6,7,8,9,10,11]:
        j = j + 1
        index = numpy.where(Mnth_daily==i)[0]
        if len(index)!=0:
            hr = Hour_daily[index]+Mnit_daily[index]/float(60)
            Fe_hr_avg = numpy.ma.average(Fe_daily[index],axis=0)
            Fe_hr_num = numpy.ma.count(Fe_daily[index],axis=0)
            if j in [1,2,3,4,5,6,7,8,9]:
                xlabel = None
            else:
                xlabel = 'Hour'
            if j in [2,3,5,6,8,9,11,12]:
                ylabel = None
            else:
                ylabel = 'Fe (W/m2)'
            hrplot(hr[0],Fe_hr_avg,sub=[4,3,j],
                   title=MnthList[i-1],xlabel=xlabel,ylabel=ylabel,
                   colours=Fe_hr_num)
    # save the plot to file
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DiurnalFeByMonth.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()
    # plot Fc
    log.info(' Doing the diurnal Fc by month plot ')
    nFig = nFig + 1
    fig = plt.figure(nFig,figsize=(PlotWidth_portrait,PlotHeight_portrait))
    fig.canvas.set_window_title("Diurnal Fc")
    plt.figtext(0.5,0.95,PlotTitle,horizontalalignment='center',size=16)
    j = 0
    for i in [12,1,2,3,4,5,6,7,8,9,10,11]:
        j = j + 1
        index = numpy.where(Mnth_daily==i)[0]
        if len(index)!=0:
            hr = Hour_daily[index]+Mnit_daily[index]/float(60)
            Fc_hr_avg = numpy.ma.average(Fc_daily[index],axis=0)
            Fc_hr_num = numpy.ma.count(Fc_daily[index],axis=0)
            if j in [1,2,3,4,5,6,7,8,9]:
                xlabel = None
            else:
                xlabel = 'Hour'
            if j in [2,3,5,6,8,9,11,12]:
                ylabel = None
            else:
                ylabel = 'Fc ('+Fc_units+')'
            hrplot(hr[0],Fc_hr_avg,sub=[4,3,j],
                   title=MnthList[i-1],xlabel=xlabel,ylabel=ylabel,
                   colours=Fc_hr_num)
    # save the plot to file
    figname='plots/'+ds.globalattributes['site_name'].replace(' ','')+'_'+ds.globalattributes['nc_level']+'_QC_'+'DiurnalFcByMonth.png'
    fig.savefig(figname,format='png')
    # draw the plot on the screen
    plt.draw()    

def plot_setup(cf,nFig):
    p = {}
    p['PlotDescription'] = cf['Plots'][str(nFig)]['Title']
    p['SeriesList'] = ast.literal_eval(cf['Plots'][str(nFig)]['Variables'])
    p['nGraphs'] = len(p['SeriesList'])
    p['PlotWidth'] = 13
    p['PlotHeight'] = 9
    p['ts_YAxOrg'] = 0.08
    p['ts_XAxOrg'] = 0.06
    p['ts_XAxLen'] = 0.6
    p['hr_XAxLen'] = 0.1
    p['ts_YAxLen'] = (0.85 - (p['nGraphs'] - 1)*0.02)/p['nGraphs']
    p['yaxOrgOffset'] = (0.85 - p['ts_YAxLen'])/(p['nGraphs'] - 1)
    p['hr1_XAxOrg'] = p['ts_XAxOrg']+p['ts_XAxLen']+0.07
    p['hr1_XAxLen'] = p['hr_XAxLen']
    p['hr2_XAxOrg'] = p['hr1_XAxOrg']+p['hr1_XAxLen']+0.05
    p['hr2_XAxLen'] = p['hr_XAxLen']
    p['bar_XAxOrg'] = p['hr1_XAxOrg']+p['hr1_XAxLen']+0.05+p['hr1_XAxLen']+0.05
    p['bar_XAxLen'] = p['hr_XAxLen']
    return p

def plot_onetimeseries_left(fig,n,ThisOne,xarray,yarray,p):
    ts_ax = fig.add_axes([p['ts_XAxOrg'],p['YAxOrg'],p['ts_XAxLen'],p['ts_YAxLen']])
    ts_ax.hold(False)
    p['ts_ax'] = ts_ax
    ts_ax.plot(xarray,yarray,'b-')
    ts_ax.xaxis.set_major_locator(p['loc'])
    ts_ax.xaxis.set_major_formatter(p['fmt'])
    ts_ax.set_xlim(p['XAxMin'],p['XAxMax'])
    ts_ax.set_ylim(p['LYAxMin'],p['LYAxMax'])
    if n==0:
        ts_ax.set_xlabel('Date',visible=True)
    else:
        ts_ax.set_xlabel('',visible=False)
    TextStr = ThisOne+'('+p['Units']+')'+str(p['nRecs'])+' '+str(p['nNotM'])+' '+str(p['nMskd'])
    txtXLoc = p['ts_XAxOrg']+0.01
    txtYLoc = p['YAxOrg']+p['ts_YAxLen']-0.025
    plt.figtext(txtXLoc,txtYLoc,TextStr,color='b',horizontalalignment='left')
    if n > 0: plt.setp(ts_ax.get_xticklabels(),visible=False)

def plot_onetimeseries_right(fig,n,ThisOne,xarray,yarray,p):
    if not p.has_key('ts_ax'):
        ts_ax = fig.add_axes([p['ts_XAxOrg'],p['YAxOrg'],p['ts_XAxLen'],p['ts_YAxLen']])
        ts_ax.hold(False)
        ts_ax.yaxis.tick_right()
        TextStr = ThisOne+'('+p['Units']+')'
        txtXLoc = p['ts_XAxOrg']+0.01
        txtYLoc = p['YAxOrg']+p['ts_YAxLen']-0.025
        plt.figtext(txtXLoc,txtYLoc,TextStr,color='b',horizontalalignment='left')
    else:
        ts_ax = p['ts_ax'].twinx()
    colour = 'r'
    if p.has_key('ts_ax'): del p['ts_ax']
    ts_ax.plot(xarray,yarray,'r-')
    ts_ax.xaxis.set_major_locator(p['loc'])
    ts_ax.xaxis.set_major_formatter(p['fmt'])
    ts_ax.set_xlim(p['XAxMin'],p['XAxMax'])
    ts_ax.set_ylim(p['RYAxMin'],p['RYAxMax'])
    if n==0:
        ts_ax.set_xlabel('Date',visible=True)
    else:
        ts_ax.set_xlabel('',visible=False)
    TextStr = str(p['nNotM'])+' '+str(p['nMskd'])
    txtXLoc = p['ts_XAxOrg']+p['ts_XAxLen']-0.01
    txtYLoc = p['YAxOrg']+p['ts_YAxLen']-0.025
    plt.figtext(txtXLoc,txtYLoc,TextStr,color='r',horizontalalignment='right')
    if n > 0: plt.setp(ts_ax.get_xticklabels(),visible=False)

def plotxy(cf,nFig,plt_cf,dsa,dsb,si,ei):
    SiteName = dsa.globalattributes['site_name']
    PlotDescription = cf['Plots'][str(nFig)]['Title']
    fig = plt.figure(int(nFig))
    
    fig.clf()
    plt.figtext(0.5,0.95,SiteName+': '+PlotDescription,ha='center',size=16)
    XSeries = ast.literal_eval(plt_cf['XSeries'])
    YSeries = ast.literal_eval(plt_cf['YSeries'])
    log.info(' Plotting xy: '+str(XSeries)+' v '+str(YSeries))
    if dsa == dsb:
        for xname,yname in zip(XSeries,YSeries):
            xa,flag,attr = qcutils.GetSeriesasMA(dsa,xname,si=si,ei=ei)
            ya,flag,attr = qcutils.GetSeriesasMA(dsa,yname,si=si,ei=ei)
            xyplot(xa,ya,sub=[1,1,1],regr=1,xlabel=xname,ylabel=yname)
    else:
        for xname,yname in zip(XSeries,YSeries):
            xa,flag,attr = qcutils.GetSeriesasMA(dsa,xname,si=si,ei=ei)
            ya,flag,attr = qcutils.GetSeriesasMA(dsa,yname,si=si,ei=ei)
            xb,flag,attr = qcutils.GetSeriesasMA(dsb,xname,si=si,ei=ei)
            yb,flag,attr = qcutils.GetSeriesasMA(dsb,yname,si=si,ei=ei)
            xyplot(xa,ya,sub=[1,2,1],xlabel=xname,ylabel=yname)
            xyplot(xb,yb,sub=[1,2,2],regr=1,xlabel=xname,ylabel=yname)
    fig.show()

def xyplot(x,y,sub=[1,1,1],regr=0,thru0=0,title=None,xlabel=None,ylabel=None,fname=None):
    '''Generic XY scatter plot routine'''
    wspace = 0.0
    hspace = 0.0
    plt.subplot(sub[0],sub[1],sub[2])
    plt.plot(x,y,'b.')
    ax = plt.gca()
    if xlabel!=None: plt.xlabel(xlabel)
    if ylabel!=None:
        plt.ylabel(ylabel)
        wspace = 0.3
    if title!=None:
        plt.title(title)
        hspace = 0.3
    if regr==1:
        coefs = numpy.ma.polyfit(numpy.ma.copy(x),numpy.ma.copy(y),1)
        xfit = numpy.ma.array([numpy.ma.minimum(x),numpy.ma.maximum(x)])
        yfit = numpy.polyval(coefs,xfit)
        r = numpy.ma.corrcoef(x,y)
        eqnstr = 'y = %.3fx + %.3f, r = %.3f'%(coefs[0],coefs[1],r[0][1])
        plt.plot(xfit,yfit,'r--',linewidth=3)
        plt.text(0.5,0.925,eqnstr,fontsize=8,horizontalalignment='center',transform=ax.transAxes)
    elif regr==2:
        mask = (x.mask)|(y.mask)
        x.mask = mask
        y.mask = mask
        x_nm = numpy.ma.compressed(x)
        x_nm = sm.add_constant(x_nm,prepend=False)
        y_nm = numpy.ma.compressed(y)
        if len(y_nm)!=0 or len(x_nm)!=0:
            resrlm = sm.RLM(y_nm,x_nm,M=sm.robust.norms.TukeyBiweight()).fit()
            eqnstr = 'y = %.3fx + %.3f'%(resrlm.params[0],resrlm.params[1])
            plt.plot(x_nm[:,0],resrlm.fittedvalues,'r--',linewidth=3)
            plt.text(0.5,0.9,eqnstr,fontsize=8,horizontalalignment='center',transform=ax.transAxes)
        else:
            log.info("xyplot: nothing to plot!")
    if thru0!=0:
        x = x[:,numpy.newaxis]
        a, _, _, _ = numpy.linalg.lstsq(x, y)
        eqnstr = 'y = %.3fx'%(a)
        plt.text(0.5,0.875,eqnstr,fontsize=8,horizontalalignment='center',transform=ax.transAxes)
    plt.subplots_adjust(wspace=wspace,hspace=hspace)

def hrplot(x,y,sub=[1,1,1],title=None,xlabel=None,ylabel=None,colours=None):
    plt.subplot(sub[0],sub[1],sub[2])
    if (y.all() is numpy.ma.masked):
        y = numpy.ma.zeros(len(y))
    if colours!=None:
        plt.scatter(x,y,c=colours)
    else:
        plt.scatter(x,y)
    plt.xlim(0,24)
    plt.xticks([0,6,12,18,24])
    if title!=None:
        plt.title(title)
    if ylabel!=None:
        plt.ylabel(ylabel)
    if xlabel!=None:
        plt.xlabel(xlabel)

def tsplot(x,y,sub=[1,1,1],title=None,xlabel=None,ylabel=None,colours=None,lineat=None):
    plt.subplot(sub[0],sub[1],sub[2])
    MTFmt = mdt.DateFormatter('%d/%m')
    if (y.all() is numpy.ma.masked):
        y = numpy.ma.zeros(len(y))
    if colours!=None:
        plt.scatter(x,y,c=colours)
    else:
        plt.scatter(x,y)
    if lineat!=None:
        plt.plot((x[0],x[-1]),(float(lineat),float(lineat)))
    plt.xlim((x[0],x[-1]))
    ax = plt.gca()
    ax.xaxis.set_major_formatter(MTFmt)
    if title!=None:
        plt.title(title)
    if ylabel!=None:
        ax.yaxis.set_label_text(ylabel)
    if xlabel!=None:
        ax.xaxis.set_label_text(xlabel)