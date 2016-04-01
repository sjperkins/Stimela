import os
import sys
import numpy

sys.path.append("/utils")
import utils

CONFIG = os.environ["CONFIG"]
INPUT = os.environ["INPUT"]
OUTPUT = os.environ["OUTPUT"]
MSDIR = os.environ["MSDIR"]

jdict = dict(npix=2048, nfacets=11, MaxMajorIter=5, cellsize=5, Enable=False)

jdict.update( utils.readJson(CONFIG) )


def find_closest(A, target):
    #A must be sorted
    idx = A.searchsorted(target)
    idx = numpy.clip(idx, 1, len(A)-1)
    left = A[idx-1]
    right = A[idx]
    idx -= target - left < right - target
    return idx


STANDARD_OPTS = {
    "field_id" : "Field",
    "spw_id" : "DDID",
    "prefix" : "ImageName",
    "weight" : "Weighting",
    "robust" : "Robust",
    "npix" : "Npix",
    "cellsize": "Cell",
    "nfacets" : "NFacets",
    "column" : "ColName",
}

niter = jdict.pop("clean_iterations", 0)

mode = "Dirty"
if niter:
    mode = "Clean"

if jdict.pop("predict", False):
    skymodel = jdict.pop("skymodel", None)
    if skymodel:
        mode = "Predict"
        skymodel = INPUT + "/" + skymodel


msname = jdict.pop("msname")
prefix = OUTPUT + "/" + jdict.pop("imageprefix", os.path.basename(msname)[:-3])
msname = MSDIR + "/" + msname

options = {}
options["MSName"] = msname
options["ImageName"] = prefix
options["SaveIms"] = "[Dirty]"
if niter:
    options["MaxMinorIter"] = niter

for key, value in jdict.iteritems():
    key = STANDARD_OPTS.get(key, key)

    if value:
        options[key] = value
    if key in options and options[key] == None:
        del options[key]

if options.pop("add_beam", False):
    pattern = options.pop("beam_files_pattern", None)
    if pattern:
        options["BeamModel"] = "FITS"
        options["FITSLAxis"] = options.pop("fits_l_axis", "L")
        options["FITSMAxis"] = options.pop("fits_m_axis", "M")
        options["FITSFile"] = "'%s/%s'"%(INPUT, pattern)


if mode=="Predict":
    import pyfits
    
    odds = numpy.array([65,75,77,81,91,99,105,117,125,135,143,147,165,175,189,195,225,231,243,245,273,275,297,315,325,343,351,375,385,405,429,441,455,495,525,539,567,585,625,637,675,693,715,729,735,819,825,875,891,945,975,1001,1029,1053,1125,1155,1215,1225,1287,1323,1365,1375,1485,1575,1617,1625,1701,1715,1755,1875,1911,1925,2025,2079,2145,2187,2205,2275,2401,2457,2475,2625,2673,2695,2835,2925,3003,3087,3125,3159,3185,3375,3465,3575,3645,3675,3773,3861,3969,4095,4125,4375,4455,4459,4725,4851,4875,5005,5103,5145,5265,5625,5733,5775,6075,6125,6237,6435,6561,6615,6825,6875,7007,7203,7371,7425,7875,8019,8085,8125,8505,8575,8775,9009,9261,9375,9477,9555,9625,10125,10395,10725,10935,11025,11319,11375,11583,11907,12005,12285,12375,13125,13365,13377,13475,14175,14553,14625,15015,15309,15435,15625,15795,15925,16807,16875,17199,17325,17875,18225,18375,18711,18865,19305,19683,19845])
    
    hdu = pyfits.open(skymodel)
    nx = hdu[0].header["naxis1"]
    ny = hdu[0].header["naxis2"]
    ndim = hdu[0].header["naxis"]
    cell = abs(hdu[0].header["cdelt1"])*3600
    ra0 = hdu[0].header["crval1"]
    dec0 = hdu[0].header["crval2"]

    recenter = options.pop("recenter", False)
        
    idx = find_closest(odds, nx)
    if odds[idx]<nx:
        tx = odds[idx + 1]
    else:
        tx = odds[idx]

    idy = find_closest(odds, ny)
    if odds[idy]<ny:
        ty = odds[idy + 1]
    else:
        ty = odds[idy]

    pad_width = numpy.zeros([ndim,2], dtype=int).tolist()

    dfx = tx - nx
    if dfx%2!=0:
        ax = dfx - dfx/2 * 2
    else:
        ax = 0
    pad_width[-1] = (dfx/2, dfx/2 + ax)


    dfy = ty - ny
    if dfx%2!=0:
        ay = dfy - dfy/2 * 2
    else:
        ay = 0
    pad_width[-2] = (dfy/2, dfy/2 + ay)

    data = numpy.pad( hdu[0].data, 
                             pad_width=pad_width, 
                             mode="constant", constant_values=0)

    hdu.close()

    options["Mode"] = "Dirty"
    options["Npix"] = data.shape[-1]
    options["Cell"] = cell

    cmd = [ "--%s=%s"%(key, value) for (key, value) in options.iteritems() ]
    utils.xrun("DDF.py", cmd)

    with pyfits.open("%s.dirty.fits"%prefix) as hdu:
        hdu[0].data = data
        if recenter:
            pass
        else:
            hdu[0].header["crval1"] = ra0
            hdu[0].header["crval2"] = dec0

        hdu[0].writeto("%s.dirty.fits"%prefix, clobber=True)

    options["Mode"] = "Predict"
    options["PredictModelName"] = "%s.dirty.fits"%prefix

    cmd = [ "--%s=%s"%(key, value) for (key, value) in options.iteritems() ]
    utils.xrun("DDF.py", cmd)

else:
    options["Mode"] = mode
    cmd = [ "--%s=%s"%(key, value) for (key, value) in options.iteritems() ]
    utils.xrun("DDF.py", cmd)