#!/usr/bin/env python
# -*- coding: latin-1; -*-
#
# FSICoupler.py
# Main file (Python core) of CUPyDO.
# Authors : David THOMAS, Marco Lucio CERQUAGLIA, Romain BOMAN
#
# COPYRIGHT (C) University of Liège, 2017.

# ----------------------------------------------------------------------
#  Imports
# ----------------------------------------------------------------------

from math import *
import numpy as np
import scipy as sp
from scipy import spatial
import scipy.sparse.linalg as splinalg
import os, os.path, sys, string
import time as tm

import traceback

import socket, fnmatch
import fsi_pyutils

import copy

import ccupydo

np.set_printoptions(threshold=np.nan)

# global vars (underscore prevent them to be imported with "from module import *")
_theModule  = None
_theWDir    = None # workspace directory
_theWDirRoot = os.getcwd()  # base directory du workspace

# ----------------------------------------------------------------------
#    Manager class
# ----------------------------------------------------------------------

class Manager(ccupydo.CManager):
    """
    Manager of CUPyDO.
    Handle MPI partitioning and gather fluid-struture interface information.
    Inherited public members :
        -setGlobalIndexing()
        -getGlobalIndex()
    """

    def __init__(self, FluidSolver, SolidSolver, nDim, computationType='steady', mpiComm=None):
        """
        Description.
        """

        ccupydo.CManager.__init__(self)

        mpiPrint('\n***************************** Initializing FSI interface *****************************', mpiComm)

        if mpiComm != None:
            self.mpiComm = mpiComm
            myid = mpiComm.Get_rank()
            mpiSize = mpiComm.Get_size()
        else:
            self.mpiComm = None
            myid = 0
            mpiSize = 1

        # --- Initialize all the parameters --- #
        self.nDim = nDim
        self.computationType = computationType
        self.withFsi = True
        self.withCht = False

        self.haveFluidSolver = False
        self.nLocalFluidInterfaceNodes = 0
        self.nLocalFluidInterfacePhysicalNodes = 0
        self.haveFluidInterface = False
        self.fluidHaloNodesList = {}
        self.fluidIndexing = {}


        self.haveSolidSolver = False
        self.nLocalSolidInterfaceNodes = 0
        self.nLocalSolidInterfacePhysicalNodes = 0
        self.haveSolidInterface = False
        self.solidHaloNodesList = {}
        self.solidIndexing = {}

        # --- Identify the fluid and solid interfaces and store the number of nodes on both sides (and for each partition) ---

        if FluidSolver != None:
            print('Fluid solver is initialized on process {}'.format(myid))
            self.haveFluidSolver = True
            self.nLocalFluidInterfaceNodes = FluidSolver.nNodes
            if self.nLocalFluidInterfaceNodes != 0:
                self.haveFluidInterface = True
                print('Number of interface fluid nodes (halo nodes included) on proccess {} : {}'.format(myid,self.nLocalFluidInterfaceNodes))
        else:
            pass

        if SolidSolver != None:
            print('Solid solver is initialized on process {}'.format(myid))
            self.haveSolidSolver = True
            self.nLocalSolidInterfaceNodes = SolidSolver.nNodes
            if self.nLocalSolidInterfaceNodes != 0:
                self.haveSolidInterface = True
                print('Number of interface solid nodes (halo nodes included) on proccess {} : {}'.format(myid,self.nLocalSolidInterfaceNodes))
        else:
            pass

        # --- Exchange information about processors on which the solvers are defined and where the interface nodes are lying --- #
        if self.mpiComm != None:
            if self.haveFluidSolver == True:
                sendBufFluid = myid
            else:
                sendBufFluid = -1
            if self.haveSolidSolver == True:
                sendBufSolid = myid
            else:
                sendBufSolid = -1
            if self.haveFluidInterface == True:
                sendBufFluidInterface = myid
            else:
                sendBufFluidInterface = -1
            if self.haveSolidInterface == True:
                sendBufSolidInterface = myid
            else :
                sendBufSolidInterface = -1
            rcvBufFluid = mpiAllGather(mpiComm, sendBufFluid)
            rcvBufSolid = mpiAllGather(mpiComm, sendBufSolid)
            rcvBufFluidInterface = mpiAllGather(mpiComm, sendBufFluidInterface)
            rcvBufSolidInterface = mpiAllGather(mpiComm, sendBufSolidInterface)
            self.fluidSolverProcessors = rcvBufFluid[rcvBufFluid != -1]
            self.solidSolverProcessors = rcvBufSolid[rcvBufSolid != -1]
            self.fluidInterfaceProcessors = rcvBufFluidInterface[rcvBufFluidInterface != -1]
            self.solidInterfaceProcessors = rcvBufSolidInterface[rcvBufSolidInterface != -1]
        else:
            self.fluidSolverProcessors = np.zeros(1, dtype=int)
            self.solidSolverProcessors = np.zeros(1, dtype=int)
            self.fluidInterfaceProcessors = np.zeros(1, dtype=int)
            self.solidInterfaceProcessors = np.zeros(1, dtype=int)
        mpiBarrier(mpiComm)

        # --- Get the list of the halo nodes on the f/s interface --- #
        self.fluidHaloNodesList = FluidSolver.haloNodeList
        if myid in self.solidSolverProcessors:
            self.solidHaloNodesList = SolidSolver.haloNodeList
        if self.mpiComm != None:
            self.fluidHaloNodesList = self.mpiComm.allgather(self.fluidHaloNodesList)
            self.solidHaloNodesList = self.mpiComm.allgather(self.solidHaloNodesList)
        else:
            self.fluidHaloNodesList = [{}]
            self.solidHaloNodesList = [{}]

        # --- Get the number of physical (= not halo) nodes on the f/s interface --- #
        self.nLocalFluidInterfacePhysicalNodes = FluidSolver.nPhysicalNodes
        if myid in self.solidSolverProcessors:
            self.nLocalSolidInterfacePhysicalNodes = SolidSolver.nPhysicalNodes

        # --- Calculate the total (sum over all partitions) number of nodes at the f/s interface --- #
        self.nFluidInterfaceNodes = mpiAllReduce(mpiComm, self.nLocalFluidInterfaceNodes)
        self.nFluidInterfacePhysicalNodes = mpiAllReduce(mpiComm, self.nLocalFluidInterfacePhysicalNodes)
        self.nSolidInterfaceNodes = mpiAllReduce(mpiComm, self.nLocalSolidInterfaceNodes)
        self.nSolidInterfacePhysicalNodes = mpiAllReduce(mpiComm, self.nLocalSolidInterfacePhysicalNodes)
        mpiPrint('Total number of fluid interface nodes (halo nodes included) : {}'.format(self.nFluidInterfaceNodes), mpiComm)
        mpiPrint('Total number of solid interface nodes (halo nodes included) : {}'.format(self.nSolidInterfaceNodes), mpiComm)
        mpiPrint('Total number of fluid interface nodes : {}'.format(self.nFluidInterfacePhysicalNodes), mpiComm)
        mpiPrint('Total number of solid interface nodes : {}'.format(self.nSolidInterfacePhysicalNodes), mpiComm)

        # --- Store the number of physical interface nodes on each processor and allgather the information --- #
        self.fluidPhysicalInterfaceNodesDistribution = np.zeros(mpiSize, dtype=int)
        self.solidPhysicalInterfaceNodesDistribution = np.zeros(mpiSize, dtype=int)
        if self.mpiComm != None:
            self.fluidPhysicalInterfaceNodesDistribution = mpiAllGather(self.mpiComm, self.nLocalFluidInterfacePhysicalNodes)
            self.solidPhysicalInterfaceNodesDistribution = mpiAllGather(self.mpiComm, self.nLocalSolidInterfacePhysicalNodes)
        else:
            self.fluidPhysicalInterfaceNodesDistribution[0] = self.nFluidInterfacePhysicalNodes
            self.solidPhysicalInterfaceNodesDistribution[0] = self.nSolidInterfacePhysicalNodes

        # --- Calculate and store the global indexing of interface physical nodes
        if self.mpiComm != None:
            fluidGlobalIndexRange_temp = tuple()
            solidGlobalIndexRange_temp = tuple()
            if myid in self.fluidInterfaceProcessors:
                globalIndexStart = 0
                for iProc in range(myid):
                    globalIndexStart += self.fluidPhysicalInterfaceNodesDistribution[iProc]
                globalIndexStop = globalIndexStart + self.nLocalFluidInterfacePhysicalNodes-1
            else:
                globalIndexStart = 0
                globalIndexStop = 0
            fluidGlobalIndexRange_temp = (globalIndexStart,globalIndexStop)
            self.fluidGlobalIndexRange = self.mpiComm.allgather(fluidGlobalIndexRange_temp)
            self.setGlobalIndexing("fluid", self.fluidGlobalIndexRange)
            if myid in self.solidInterfaceProcessors:
                globalIndexStart = 0
                for jProc in range(myid):
                    globalIndexStart += self.solidPhysicalInterfaceNodesDistribution[jProc]
                globalIndexStop = globalIndexStart + self.nLocalSolidInterfaceNodes-1
            else:
                globalIndexStart = 0
                globalIndexStop = 0
            solidGlobalIndexRange_temp = (globalIndexStart,globalIndexStop)
            self.solidGlobalIndexRange = self.mpiComm.allgather(solidGlobalIndexRange_temp)
            self.setGlobalIndexing("solid", self.solidGlobalIndexRange)
        else:
            temp = (0,self.nLocalFluidInterfacePhysicalNodes-1)
            self.fluidGlobalIndexRange = list()
            self.fluidGlobalIndexRange.append(temp)
            temp = (0,self.nSolidInterfacePhysicalNodes-1)
            self.solidGlobalIndexRange = list()
            self.solidGlobalIndexRange.append(temp)

        # --- Map the FSI indexing with the solvers indexing --- #
        fluidIndexing_temp = {}
        localIndex = 0
        for iVertex in range(self.nLocalFluidInterfaceNodes):
            nodeIndex = FluidSolver.getNodalIndex(iVertex)
            if nodeIndex in self.fluidHaloNodesList[myid].keys():
                pass
            else:
                fluidIndexing_temp[nodeIndex] = self.getGlobalIndex('fluid', myid, localIndex)
                localIndex += 1

        solidIndexing_temp = {}
        localIndex = 0
        for jVertex in range(self.nLocalSolidInterfaceNodes):
            nodeIndex = SolidSolver.getNodalIndex(jVertex)
            if nodeIndex in self.solidHaloNodesList[myid].keys():
                pass
            else:
                solidIndexing_temp[nodeIndex] = self.getGlobalIndex('solid', myid, localIndex)
                localIndex += 1

        if self.mpiComm != None:
            fluidIndexing_temp = self.mpiComm.allgather(fluidIndexing_temp)
            solidIndexing_temp = self.mpiComm.allgather(solidIndexing_temp)
            for ii in range(len(solidIndexing_temp)):
                for key, value in solidIndexing_temp[ii].items():
                    self.solidIndexing[key] = value
            for ii in range(len(fluidIndexing_temp)):
                for key, value in fluidIndexing_temp[ii].items():
                    self.fluidIndexing[key] = value
        else:
            self.fluidIndexing = fluidIndexing_temp.copy()
            self.solidIndexing = solidIndexing_temp.copy()
        del fluidIndexing_temp, solidIndexing_temp

    def getGlobalIndex(self, domain, iProc, iLocalVertex):
        """
        Description.
        """

        if domain == 'fluid':
            globalStartIndex = self.fluidGlobalIndexRange[iProc][0]
        elif domain == 'solid':
            globalStartIndex = self.solidGlobalIndexRange[iProc][0]
        globalIndex = globalStartIndex + iLocalVertex

        return globalIndex

    def getNumberOfFluidInterfaceNodes(self):
        """
        Description.
        """

        return self.nFluidInterfacePhysicalNodes

    def getNumberOfLocalFluidInterfaceNodes(self):
        """
        Description.
        """

        return self.nLocalFluidInterfacePhysicalNodes

    def getNumberOfSolidInterfaceNodes(self):
        """
        Description.
        """

        return self.nSolidInterfacePhysicalNodes

    def getNumberOfLocalSolidInterfaceNodes(self):
        """
        Description.
        """

        return self.nLocalSolidInterfacePhysicalNodes

    def getSolidSolverProcessors(self):
        """
        Des.
        """

        return self.solidSolverProcessors

    def getSolidInterfaceProcessors(self):
        """
        Description.
        """

        return self.solidInterfaceProcessors

    def getFluidInterfaceProcessors(self):
        """
        Description.
        """

        return self.fluidInterfaceProcessors

    def getSolidPhysicalInterfaceNodesDistribution(self):
        """
        Des.
        """

        return self.solidPhysicalInterfaceNodesDistribution

    def getFluidPhysicalInterfaceNodesDistribution(self):
        """
        Des.
        """

        return self.fluidPhysicalInterfaceNodesDistribution

    def getSolidGlobalIndexRange(self):
        """
        Des.
        """

        return self.solidGlobalIndexRange

    def getFluidGlobalIndexRange(self):
        """
        Des.
        """

        return self.fluidGlobalIndexRange

    def getFluidHaloNodesList(self):
        """
        Des.
        """

        return self.fluidHaloNodesList

    def getSolidHaloNodesList(self):
        """
        Des.
        """

        return self.solidHaloNodesList

    def getFluidIndexing(self):
        """
        Des.
        """

        return self.fluidIndexing

    def getSolidIndexing(self):
        """
        Des.
        """

        return self.solidIndexing

    def getnDim(self):
        """
        Des.
        """

        return self.nDim

    def getComputationType(self):
        """
        des.
        """

        return self.computationType

    def getMPIComm(self):
        """
        Description.
        """

        return self.mpiComm
