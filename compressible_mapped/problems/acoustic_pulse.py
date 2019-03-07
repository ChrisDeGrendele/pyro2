from __future__ import print_function

# import sys
import numpy as np
import sympy
from sympy.abc import x, y

from util import msg
# import mesh.fv as fv


def init_data(myd, rp):
    """initialize the acoustic_pulse problem.  This comes from
    McCourquodale & Coella 2011"""

    msg.bold("initializing the acoustic pulse problem...")

    # # make sure that we are passed a valid patch object
    # if not isinstance(myd, fv.FV2d):
    #     print("ERROR: patch invalid in acoustic_pulse.py")
    #     print(myd.__class__)
    #     sys.exit()

    # get the density, momenta, and energy as separate variables
    dens = myd.get_var("density")
    xmom = myd.get_var("x-momentum")
    ymom = myd.get_var("y-momentum")
    ener = myd.get_var("energy")

    # initialize the components, remember, that ener here is rho*eint
    # + 0.5*rho*v**2, where eint is the specific internal energy
    # (erg/g)
    xmom[:, :] = 0.0
    ymom[:, :] = 0.0

    gamma = rp.get_param("eos.gamma")

    rho0 = rp.get_param("acoustic_pulse.rho0")
    drho0 = rp.get_param("acoustic_pulse.drho0")

    xmin = rp.get_param("mesh.xmin")
    xmax = rp.get_param("mesh.xmax")

    ymin = rp.get_param("mesh.ymin")
    ymax = rp.get_param("mesh.ymax")

    myg = myd.grid

    X, Y = myg.physical_coords()

    # rather than map the center of the coordinate grid, find the center by
    # locating the center of a diagonal across the physical domain
    xctr_t, yctr_t = 0.5 * \
        (myg.physical_coords(xmin, ymin) + myg.physical_coords(xmax, ymax))

    dist = np.sqrt((X - xctr_t)**2 + (Y - yctr_t)**2)

    dens[:, :] = rho0
    idx = dist <= 0.5
    dens[idx] = rho0 + drho0 * \
        np.exp(-16 * dist[idx]**2) * np.cos(np.pi * dist[idx])**6

    p = (dens / rho0)**gamma
    ener[:, :] = p / (gamma - 1)


def sym_map(myg):

    return sympy.Matrix([y**2, -2 * x**2 - y])

    # return sympy.Matrix([x * sympy.cos(y), x * sympy.sin(y)])


def finalize():
    """ print out any information to the user at the end of the run """
    pass