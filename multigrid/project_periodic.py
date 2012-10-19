#!/usr/bin/env python

# test of a cell-centered, centered-difference approximate projection.
#
# initialize the velocity field to be divergence free and then add to
# it the gradient of a scalar (whose normal component vanishes on the
# boundaries).  The projection should recover the original divergence-
# free velocity field.
#
# The test velocity field comes from Almgen, Bell, and Szymczak 1996.
#
# This makes use of the multigrid solver with periodic boundary conditions.
#
# One of the things that this test demonstrates is that the initial
# projection may not be able to completely remove the divergence free
# part, so subsequent projections may be necessary.  In this example,
# we add a very strong gradient component.
#
# The total number of projections to perform is given by nproj.  Each
# projection uses the divergence of the velocity field from the previous
# iteration as its source term.

import numpy
import multigrid
import mesh.patch as patch
import math


# the L2 error norm
def error(myg, r):

    # L2 norm of elements in r, multiplied by dx to
    # normalize
    return numpy.sqrt(myg.dx*myg.dy*numpy.sum((r[myg.ilo:myg.ihi+1,myg.jlo:myg.jhi+1]**2).flat))


        
nx = 128
ny = 128

nproj = 3

# create a mesh containing the x- and y-velocities, and periodic boundary
# conditions
myg = patch.grid2d(nx, ny, ng=1)

bcObj = patch.bcObject(xlb="periodic", xrb="periodic",
                       ylb="periodic", yrb="periodic")

U = patch.ccData2d(myg)

U.registerVar('u', bcObj)
U.registerVar('v', bcObj)
U.registerVar('u-old', bcObj)
U.registerVar('v-old', bcObj)
U.registerVar('phi-old', bcObj)
U.registerVar('gradphi_x-old', bcObj)
U.registerVar('gradphi_y-old', bcObj)
U.registerVar('divU', bcObj)
U.registerVar('phi', bcObj)
U.registerVar('gradphi_x', bcObj)
U.registerVar('gradphi_y', bcObj)
U.registerVar('dphi', bcObj)
U.create()

# initialize a divergence free velocity field,
# u = -sin^2(pi x) sin(2 pi y), v = sin^2(pi y) sin(2 pi x)
u = U.getVarPtr('u')
v = U.getVarPtr('v')

u[:,:] = -(numpy.sin(math.pi*myg.x2d)**2)*numpy.sin(2.0*math.pi*myg.y2d)
v[:,:] =  (numpy.sin(math.pi*myg.y2d)**2)*numpy.sin(2.0*math.pi*myg.x2d)


# store the original, divergence free velocity field for comparison later
uold = U.getVarPtr('u-old')
vold = U.getVarPtr('v-old')

uold[:,:] = u.copy()
vold[:,:] = v.copy()


# the projection routine should decompose U into a divergence free
# part, U_d, plus the gradient of a scalar.  Add on the gradient of a
# scalar that satisfies gradphi.n = 0.  After the projection, we
# should recover the divergence free field above.  Take phi to be a
# gaussian, exp(-((x-x0)^2 + (y-y0)^2)/R)
R = 0.1
x0 = 0.5
y0 = 0.5

phi = U.getVarPtr('phi-old')
gradphi_x = U.getVarPtr('gradphi_x-old')
gradphi_y = U.getVarPtr('gradphi_y-old')

phi[:,:] = numpy.exp(-((myg.x2d-x0)**2 + (myg.y2d-y0)**2)/R**2)

gradphi_x[:,:] = phi*(-2.0*(myg.x2d-x0)/R**2)
gradphi_y[:,:] = phi*(-2.0*(myg.y2d-y0)/R**2)

u += gradphi_x
v += gradphi_y


# use the mesh class to enforce the periodic BCs on the velocity field
U.fillBCAll()


# now compute the cell-centered, centered-difference divergence
divU = U.getVarPtr('divU')

divU[myg.ilo:myg.ihi+1,myg.jlo:myg.jhi+1] = \
        0.5*(u[myg.ilo+1:myg.ihi+2,myg.jlo  :myg.jhi+1] -
             u[myg.ilo-1:myg.ihi  ,myg.jlo  :myg.jhi+1])/myg.dx + \
        0.5*(v[myg.ilo  :myg.ihi+1,myg.jlo+1:myg.jhi+2] -
             v[myg.ilo  :myg.ihi+1,myg.jlo-1:myg.jhi  ])/myg.dy



# create the multigrid object with Neumann BCs
MG = multigrid.ccMG2d(nx, ny,
                      xlBCtype="periodic", xrBCtype="periodic",
                      ylBCtype="periodic", yrBCtype="periodic",
                      verbose=1)


#----------------------------------------------------------------------------
# projections
#----------------------------------------------------------------------------
iproj = 1
while (iproj <= nproj):

    MG.initZeros()
    MG.initRHS(divU)
    MG.solve(rtol=1.e-12)

    phi = U.getVarPtr('phi')
    solution = MG.getSolution()

    phi[myg.ilo-1:myg.ihi+2,myg.jlo-1:myg.jhi+2] = \
        solution[MG.ilo-1:MG.ihi+2,MG.jlo-1:MG.jhi+2]

    dphi = U.getVarPtr('dphi')
    dphi[:,:] = phi - U.getVarPtr('phi-old')


    # compute the gradient of phi using centered differences
    gradphi_x = U.getVarPtr('gradphi_x')
    gradphi_y = U.getVarPtr('gradphi_y')

    gradphi_x[myg.ilo:myg.ihi+1,myg.jlo:myg.jhi+1] = \
        0.5*(phi[myg.ilo+1:myg.ihi+2,myg.jlo:myg.jhi+1] -
             phi[myg.ilo-1:myg.ihi,myg.jlo:myg.jhi+1])/myg.dx

    gradphi_y[myg.ilo:myg.ihi+1,myg.jlo:myg.jhi+1] = \
        0.5*(phi[myg.ilo:myg.ihi+1,myg.jlo+1:myg.jhi+2] -
             phi[myg.ilo:myg.ihi+1,myg.jlo-1:myg.jhi])/myg.dy


    # update the velocity field
    u -= gradphi_x
    v -= gradphi_y

    U.fillBCAll()


    # recompute the divergence diagnostic
    divU[myg.ilo:myg.ihi+1,myg.jlo:myg.jhi+1] = \
        0.5*(u[myg.ilo+1:myg.ihi+2,myg.jlo:myg.jhi+1] -
             u[myg.ilo-1:myg.ihi,myg.jlo:myg.jhi+1])/myg.dx + \
        0.5*(v[myg.ilo:myg.ihi+1,myg.jlo+1:myg.jhi+2] -
             v[myg.ilo:myg.ihi+1,myg.jlo-1:myg.jhi])/myg.dy


    U.write("proj-periodic.after"+("%d" % iproj))

    iproj += 1


