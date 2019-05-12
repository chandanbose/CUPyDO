#! /usr/bin/env python
# -*- coding: utf-8 -*-
# original name: 

''' 

Copyright 2018 University of Liège

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License. 

'''

import os, sys

filePath = os.path.abspath(os.path.dirname(__file__))
fileName = os.path.splitext(os.path.basename(__file__))[0]


from math import *
from optparse import OptionParser

import cupydo.utilities as cupyutil
import cupydo.manager as cupyman
import cupydo.interpolator as cupyinterp
import cupydo.criterion as cupycrit
import cupydo.algorithm as cupyalgo

import numpy as np
from cupydo.testing import *

def getParameters(_p):
    # --- Input parameters --- #
    p = {}
    p['nthreads'] = 1
    p['nDim'] = 2
    p['tollFSI'] = 1e-6
    p['dt'] = 0.001
    p['tTot'] = 0.05
    p['nFSIIterMax'] = 20
    p['timeIterTreshold'] = 0
    p['omegaMax'] = 0.5
    p['computationType'] = 'unsteady'
    p['nbTimeToKeep'] = 0
    p['computeTangentMatrixBasedOnFirstIt'] = False
    p['saveFreqPFEM'] = 10
    p['mtfSaveAllFacs'] = False
    p.update(_p)
    return p

def main(_p, nogui): # NB, the argument 'nogui' is specific to PFEM only!
    
    p = getParameters(_p)

    # --- Set up MPI --- #
    withMPI, comm, myid, numberPart = cupyutil.getMpi()
    rootProcess = 0
    
    # --- Input parameters --- #
    cfd_file = 'rho1100_fluid'
    csd_file = 'rho1100_solid'
    
    # --- Initialize the fluid solver --- #
    import cupydo.interfaces.Pfem as fItf
    fluidSolver = fItf.Pfem(cfd_file, 17, p['dt'])
    
    # --- This part is specific to PFEM ---
    fluidSolver.pfem.scheme.nthreads = p['nthreads']
    fluidSolver.pfem.scheme.savefreq = p['saveFreqPFEM']
    if nogui:
        fluidSolver.pfem.gui = None
    # ---
    
    cupyutil.mpiBarrier(comm)
    
    # --- Initialize the solid solver --- #
    solidSolver = None
    if myid == rootProcess:
        import cupydo.interfaces.Metafor as sItf
        solidSolver = sItf.Metafor(csd_file, p['computationType'])
        
        # --- This part is specific to Metafor ---
        solidSolver.saveAllFacs = p['mtfSaveAllFacs']
        
    cupyutil.mpiBarrier(comm)
        
    # --- Initialize the FSI manager --- #
    manager = cupyman.Manager(fluidSolver, solidSolver, p['nDim'], p['computationType'], comm)
    cupyutil.mpiBarrier()

    # --- Initialize the interpolator --- #
    interpolator = cupyinterp.MatchingMeshesInterpolator(manager, fluidSolver, solidSolver, comm)
    
    # --- Initialize the FSI criterion --- #
    criterion = cupycrit.DispNormCriterion(p['tollFSI'])
    cupyutil.mpiBarrier()
    
    # --- Initialize the FSI algorithm --- #
    algorithm = cupyalgo.AlgorithmIQN_ILS(manager, fluidSolver, solidSolver, interpolator, criterion, p['nFSIIterMax'], p['dt'], p['tTot'], p['timeIterTreshold'], p['omegaMax'], p['nbTimeToKeep'], p['computeTangentMatrixBasedOnFirstIt'], comm)
    
    # --- Launch the FSI computation --- #
    algorithm.run()
    
    # --- Check the results --- #
    
    # Check convergence and results
    if (algorithm.errValue > p['tollFSI']):
        print "\n\n" + "FSI residual = " + str(algorithm.errValue) + ", FSI tolerance = " + str(p['tollFSI'])
        raise Exception(ccolors.ANSI_RED + "FSI algo failed to converge!" + ccolors.ANSI_RESET)
    
    # Read results from file
    with open("Node_9_POS.ascii", 'rb') as f:
        lines = f.readlines()
    result_1 = np.genfromtxt(lines[-1:], delimiter=None)
    
    tests = CTests()
    tests.add(CTest('Mean nb of FSI iterations', algorithm.getMeanNbOfFSIIt(), 4, 1, True)) # abs. tol. of 1
    tests.add(CTest('X-coordinate gate tip', result_1[0], 0.487164, 1e-2, False)) # rel. tol. of 1%
    tests.add(CTest('Y-coordinate gate tip', result_1[1], 0.0006501, 1e-2, False)) # rel. tol. of 1%
    tests.run()

# -------------------------------------------------------------------
#    Run Main Program
# -------------------------------------------------------------------

# --- This is only accessed if running from command prompt --- #
if __name__ == '__main__':
    
    p = {}
    
    parser=OptionParser()
    parser.add_option("--nogui", action="store_true",
                        help="Specify if we need to use the GUI", dest="nogui", default=False)
    parser.add_option("-n", type="int", help="Number of threads", dest="nthreads", default=1)
    
    
    (options, args)=parser.parse_args()
    
    nogui = options.nogui
    p['nthreads'] = options.nthreads
    
    main(p, nogui)