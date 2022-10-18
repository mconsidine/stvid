#!/usr/bin/env python3
import os
import sys
import glob
import time

import argparse
import configparser

import numpy as np

import warnings

from termcolor import colored

from stvid import calibration

#from stvid.fourframe import FourFrame
#from stvid.fourframe import Observation
#from stvid.fourframe import AstrometricCatalog

#from stvid.stars import pixel_catalog
#from stvid.stars import store_calibration
#from stvid.stars import generate_star_catalog
#from stvid.astrometry import calibrate_from_reference
#from stvid.astrometry import generate_reference_with_anet

from astropy.utils.exceptions import AstropyWarning

if __name__ == "__main__":
    # Read commandline options
    conf_parser = argparse.ArgumentParser(description="Process captured" +
                                          " video frames.")
    conf_parser.add_argument("-c",
                             "--conf_file",
                             help="Specify configuration file. If no file" +
                             " is specified 'configuration.ini' is used.",
                             metavar="FILE")
    conf_parser.add_argument("-d",
                             "--directory",
                             help="Specify directory of observations. If no" +
                             " directory is specified parent will be used.",
                             metavar="DIR",
                             dest="file_dir",
                             default=".")
    args = conf_parser.parse_args()
    
    # Read configuration file
    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ":"))
    conf_file = args.conf_file if args.conf_file else "configuration.ini"
    result = cfg.read([conf_file])
    if not result:
        print("Could not read config file: %s\nExiting..." % conf_file)
        sys.exit()

    # Set warnings
    warnings.filterwarnings("ignore", category=UserWarning, append=True)
    warnings.simplefilter("ignore", AstropyWarning)

    
    # Observer settings
    nstarsmin = cfg.getint("Processing", "nstarsmin")

    
    # Extract abbrevs for TLE files
    abbrevs, tlefiles = [], []
    for key, value in cfg.items("Elements"):
        if "tlefile" in key:
            tlefiles.append(os.path.basename(value))
        elif "abbrev" in key:
            abbrevs.append(value)

    # Read astrometric catalog
    acat = calibration.AstrometricCatalog(cfg.getfloat("Astrometry", "maximum_magnitude"))
            
    # Start processing loop
    solved = False
    while True:
        # Get files
        fnames = sorted(glob.glob(os.path.join(args.file_dir, "2*.fits")))

        # Create reference calibration file
        calfname = os.path.join(args.file_dir, "test.fits")
        if not os.path.exists(calfname):
            solved = False

            # Loop over files to find a suitable calibration file
            for fname in fnames:
                # Was this file already tried?
                if not os.path.exists(os.path.join(args.file_dir, f"{fname}.cat")):
                    # Generate star catalog
                    scat = calibration.generate_star_catalog(fname)

                    # Solve
                    if scat.nstars > nstarsmin:
                        print(colored(f"Computing astrometric calibration for {fname}", "yellow"))
                        wref, tref = calibration.plate_solve(fname, cfg, calfname)
                        if wref is not None:
                            solved = True

                    # Break when solved
                    if solved:
                        break
        else:
            # test.fits exists, so calibration has been solved
            solved = True

            # Read calibration
            wref, tref = calibration.read_calibration(calfname)

        # Loop over files
        for fname in fnames:
            # File root
            froot = os.path.splitext(fname)[0]
            
            # Find stars
            if not os.path.exists(f"{froot}.cat"):
                scat = calibration.generate_star_catalog(fname)
            else:
                scat = calibration.read_star_catalog(fname)

            # Calibrate
            if not os.path.exists(f"{froot}.wcs"):
                w, rmsx, rmsy, nused, is_calibrated = calibration.calibrate(fname, cfg, acat, scat, wref, tref)

                # Attempt plate solve
                if not is_calibrated and scat.nstars > nstarsmin:
                    print(colored(f"Computing astrometric calibration for {fname}", "yellow"))
                    wtmp, ttmp = calibration.plate_solve(fname, cfg, calfname)
                    
                    # Retry calibration
                    if wtmp is not None:
                        wref, tref = wtmp, ttmp
                        w, rmsx, rmsy, nused, is_calibrated = calibration.calibrate(fname, cfg, acat, scat, wref, tref)

                output = f"{os.path.basename(fname)},{w.wcs.crval[0]:.6f},{w.wcs.crval[1]:.6f},{rmsx:.3f},{rmsy:.3f},{nused}/{scat.nstars}"

                if is_calibrated:
                    color = "green"
                else:
                    color = "red"
                print(colored(output, color))

        # Sleep
        try:
            print("File queue empty, waiting for new files...\r", end = "")
            time.sleep(10)
        except KeyboardInterrupt:
            sys.exit()
