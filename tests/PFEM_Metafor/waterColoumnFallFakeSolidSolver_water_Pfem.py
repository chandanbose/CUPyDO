#! /usr/bin/env python
# -*- coding: latin-1; -*-

''' 

Copyright 2018 University of Li�ge

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

import sys, os, os.path

runPath = os.path.dirname(sys.modules[__name__].__file__)
filePath = os.path.abspath(os.path.dirname(sys.argv[0]))
fileName = os.path.splitext(os.path.basename(__file__))[0]

import pfem

import pfemtools as wt
import viewer as v
    
w = None

class Module:
    def __init__(self, w, msh, pbl, solScheme, nonLinAlgo, convCriterion, scheme, extManager, gui):
       self.w = w
       self.msh = msh
       self.pbl = pbl       
       self.solScheme = solScheme
       self.nonLinAlgo = nonLinAlgo
       self.convCriterion = convCriterion
       self.scheme = scheme
       self.extManager = extManager
       self.gui = gui

def getPfem():
    global w
    if w: return w
    w = pfem
    
    mshFile = runPath+os.sep+'waterColoumnFallFakeSolidSolver.msh'
    
    rho0 = 1000.
    mu = 0.001
    
    pbl = w.Problem()
    pbl.rho0 = rho0
    pbl.mu = mu
    pbl.nonLinAlgorithm = 1
    pbl.solScheme = 1
    pbl.alpha = 1.2
    pbl.extP = 100.
    pbl.scalingU = 1.0
    
    msh = w.MshData(pbl)
    msh.load(mshFile)
    print msh
    
    toll = 1e-6
    nItMax = 10
    
    solScheme = w.SchemeMonolithicPSPG(msh, pbl)
    convCriterion = w.ForcesBalanceNormedBodyForceCriterion(msh, pbl, toll)
    nonLinAlgo = w.PicardAlgorithm(solScheme, convCriterion, nItMax)
    
    scheme = w.BackwardEuler(msh, pbl, nonLinAlgo)
    
    w.Medium(msh, "Walls", mu, rho0, 3)
    w.Medium(msh, "Face1", mu, rho0, 1)
    
    # boundaries
    w.Boundary(msh, "Free", 3, pbl.extP)
    w.Boundary(msh, "Walls", 1, 0.0)
    w.Boundary(msh, "Walls", 2, 0.0)
    
    scheme.ttot = 1.0
    scheme.savefreq=1
    scheme.gamma = 0.5
    scheme.omega = 0.5
    scheme.addRemoveNodesOption = True
    scheme.tollNLalgo = 1e-12
    
    #Results
    extManager = w.ExtractorsManager(msh)
    extManager.add(1,w.PositionExtractor(msh,1))
    extManager.add(2,w.IntForceExtractor(msh,1))
    extManager.add(3,w.ExtForceExtractor(msh,1))
    extManager.add(4,w.IneForceExtractor(msh,1))
    extManager.add(5,w.IntForceExtractor(msh,6))
    extManager.add(6,w.ExtForceExtractor(msh,6))
    extManager.add(7,w.IneForceExtractor(msh,6))
    extManager.add(8,w.PressureExtractor(msh,1))
    extManager.add(9,w.VelocityExtractor(msh,"Face1"))
    extManager.add(10,w.MassExtractor(msh,pbl,"Face1"))
    extManager.add(11,wt.KineticEnergyExtractor(msh,pbl,"Face1"))
    extManager.add(12,wt.ViscousEnergyExtractor(msh,pbl,scheme,"Face1"))
    
    gui = v.MeshViewer(msh, scheme, True) 
    
    return Module(w, msh, pbl, solScheme, nonLinAlgo, convCriterion, scheme, extManager, gui)
