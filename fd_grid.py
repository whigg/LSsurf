# -*- coding: utf-8 -*-
"""
Created on Mon Dec  4 14:07:39 2017

@author: ben
"""
#import scipy.sparse as sp
import numpy as np
from osgeo import gdal 
 
class fd_grid: 
    # a fd_grid is an object that defines the nodal locations and their indices
    # for a regular grid of points. In a k-dimensional grid, each node has k
    # subscripts, and one global index.  The global index gives the index into
    # the raveled node values.  To allow multiple grids to be combined, the
    # first global index can be shifted by specifying a nonzero col_0 value,
    # and room for additional grids can be allocated by specifying a col_N value
    # that is greater than the number of nodes.
    def __init__(self, bounds, deltas, col_0=0, col_N=None, srs_WKT=None, mask_file=None, name=''):
        self.shape=np.array([((b[1]-b[0])/delta)+1 for b, delta in zip(bounds, deltas)]).astype(int)  # number of nodes in each dimension
        self.ctrs=[b[0]+ delta*np.arange(N) for b, delta, N in zip(bounds, deltas, self.shape)] # node center locations
        self.bds=[np.array([c[0], c[-1]]) for c in self.ctrs]
        self.delta=np.array(deltas)   # node spacing in each dimension
        self.N_dims=len(self.shape)  # number of dimensions
        self.N_nodes=np.prod(self.shape)  # total number of nodes
        self.stride=np.flipud(np.cumprod(np.flipud(np.r_[self.shape[1:], 1]))) # difference in global_ind between adjacent nodes
        self.col_0=col_0 # first global_ind for the grid
        self.srs_WKT=srs_WKT # Well Known Text for the spatial reference system of the grid
        self.mask_file=mask_file
        self.mask=None
        self.name=name # name of the degree of freedom specified by the grid
        if col_N is None:
            self.col_N=self.col_0+self.N_nodes
        if self.mask_file is not None:
            self.mask=self.read_geotif(self.mask_file, interp_algorithm=gdal.GRA_Average)
            self.mask=np.round(self.mask).astype(np.int)
        
    def validate_pts(self, pts):
        # check if each point is inside the grid
        good=np.isfinite(pts[0])
        for dim in range(self.N_dims):
             good[good]=np.logical_and(good[good],  pts[dim][good] >= self.bds[dim][0])
             good[good]=np.logical_and(good[good],  pts[dim][good] <= self.bds[dim][1])
        return good

    def pos_for_nodes(self, nodes):
        # find the location for a node in the grid
        pos=list()
        inds=np.unravel_index(nodes, self.shape)
        for delta, bd, ind in zip(self.delta, self.bds, inds):
            pos.append((ind*delta)+bd[0])
        return pos
        
    def float_sub(self, pts, good=None):
        # find the normalized point location within the grid (in subscript coordinates)
        idxf=[np.NaN+np.zeros_like(pts[0]) for i in range(len(pts))]
        if good is None:
            good=self.validate_pts(pts)
        for dim in range(self.N_dims):
            idxf[dim][good]=(pts[dim][good]-self.bds[dim][0])/self.delta[dim]
        return idxf
        
    def cell_sub_for_pts(self, pts, good=None):
        # find the cell number (equal to the next-smallest subscript) in each dimension
        idx0=[np.NaN+np.zeros_like(pts[0]) for i in range(len(pts))]        
        if good is None:
            good=self.validate_pts(pts)
        # report the grid indices for the cell that each point in pts falls into
        for dim in np.arange(len(self.shape)):
            idx0[dim][good]=np.floor((pts[dim][good]-self.bds[dim][0])/self.delta[dim])
        return idx0
    
    def global_ind(self, cell_sub):
        # find the global index for a particular cell number
        cell_sub=[temp.astype(int) for temp in cell_sub]
        ind=self.col_0+np.ravel_multi_index(cell_sub, self.shape)
        return ind

    def read_geotif(self, filename, srs_WKT=None, dataType=gdal.GDT_Float32, interp_algorithm=gdal.GRA_NearestNeighbour):
        # the WKT (well known text) for the grid needs to be provided as a keyword, 
        # or it can be stored in the grid
        if srs_WKT is None:
            srs_WKT=self.srs_WKT
        # the gdal geotransform gives the top left corner of each pixel.
        # define the geotransform that matches the current grid:
        #       [  x0,                                 dx,           dxy,      y0,                            dyx,     dy       ]
        this_GT=[self.ctrs[1][0]-self.delta[1]/2.,   self.delta[1], 0.,  self.ctrs[0][-1]+self.delta[0]/2, 0., -self.delta[0]]
         
        #create a dataset to hold the image information  
        memDriver=gdal.GetDriverByName('Mem')
        #                                nx,              ny,              bands,   datatype
        temp_ds=memDriver.Create('', int(self.shape[1]), int(self.shape[0]), int(1), dataType)
        temp_ds.SetProjection(srs_WKT)       
        temp_ds.SetGeoTransform(this_GT)
        
        #open the input dataset, and reproject its data onto the memory dataset
        in_ds=gdal.Open(filename)
        #in_ds.SetProjection(srs_WKT)
        gdal.ReprojectImage(in_ds, temp_ds, \
                            in_ds.GetProjection(),\
                            srs_WKT, interp_algorithm)
        # copy the data from the memory dataset into an array, z
        z=temp_ds.GetRasterBand(1).ReadAsArray(0, 0, int(self.shape[1]), int(self.shape[0]))
        # turn the invalid values in the input dataset into NaNs
        inNodata=in_ds.GetRasterBand(1).GetNoDataValue()    
        if inNodata is not None:
            z[z==inNodata]=np.NaN
        # flip z top to bottom
        z=np.flipud(z)
        
        # clean up the temporary datasets
        in_ds=None
        temp_ds=None
 
        return z
 
   