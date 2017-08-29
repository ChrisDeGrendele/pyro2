"""
Implementation of the Colella 2nd order unsplit Godunov scheme.  This
is a 2-dimensional implementation only.  We assume that the grid is
uniform, but it is relatively straightforward to relax this
assumption.

There are several different options for this solver (they are all
discussed in the Colella paper).

  limiter          = 0 to use no limiting
                   = 1 to use the 2nd order MC limiter
                   = 2 to use the 4th order MC limiter

  riemann          = HLLC to use the HLLC solver
                   = CGF to use the Colella, Glaz, and Ferguson solver

  use_flattening   = 1 to use the multidimensional flattening
                     algorithm at shocks

  delta, z0, z1      these are the flattening parameters.  The default
                     are the values listed in Colella 1990.

   j+3/2--+---------+---------+---------+
          |         |         |         |
     j+1 _|         |         |         |
          |         |         |         |
          |         |         |         |
   j+1/2--+---------XXXXXXXXXXX---------+
          |         X         X         |
       j _|         X         X         |
          |         X         X         |
          |         X         X         |
   j-1/2--+---------XXXXXXXXXXX---------+
          |         |         |         |
     j-1 _|         |         |         |
          |         |         |         |
          |         |         |         |
   j-3/2--+---------+---------+---------+
          |    |    |    |    |    |    |
              i-1        i        i+1
        i-3/2     i-1/2     i+1/2     i+3/2

We wish to solve

  U_t + F^x_x + F^y_y = H

we want U_{i+1/2}^{n+1/2} -- the interface values that are input to
the Riemann problem through the faces for each zone.

Taylor expanding yields in space only

                             dU
  U          = U   + 0.5 dx  --
   i+1/2,j,L    i,j          dx


Updating U_{i,j}:

  -- We want to find the state to the left and right (or top and
     bottom) of each interface, ex. U_{i+1/2,j,[lr]}^{n+1/2}, and use
     them to solve a Riemann problem across each of the four
     interfaces.
"""

import compressible.eos as eos
import compressible.interface_f as interface_f
import compressible as comp
import mesh.reconstruction as reconstruction
import mesh.array_indexer as ai

from util import msg

def fluxes(my_data, rp, ivars, solid, tc):
    """
    unsplitFluxes returns the fluxes through the x and y interfaces by
    doing an unsplit reconstruction of the interface values and then
    solving the Riemann problem through all the interfaces at once

    currently we assume a gamma-law EOS

    Parameters
    ----------
    my_data : CellCenterData2d object
        The data object containing the grid and advective scalar that
        we are advecting.
    rp : RuntimeParameters object
        The runtime parameters for the simulation
    vars : Variables object
        The Variables object that tells us which indices refer to which
        variables
    tc : TimerCollection object
        The timers we are using to profile

    Returns
    -------
    out : ndarray, ndarray
        The fluxes on the x- and y-interfaces

    """

    tm_flux = tc.timer("unsplitFluxes")
    tm_flux.begin()

    myg = my_data.grid

    gamma = rp.get_param("eos.gamma")

    #=========================================================================
    # compute the primitive variables
    #=========================================================================
    # Q = (rho, u, v, p)

    dens = my_data.get_var("density")
    xmom = my_data.get_var("x-momentum")
    ymom = my_data.get_var("y-momentum")
    ener = my_data.get_var("energy")

    q = comp.cons_to_prim(my_data.data, gamma, ivars, myg)


    #=========================================================================
    # compute the flattening coefficients
    #=========================================================================

    # there is a single flattening coefficient (xi) for all directions
    use_flattening = rp.get_param("compressible.use_flattening")

    if use_flattening:
        xi_x = reconstruction.flatten(myg, q, 1, ivars, rp)
        xi_y = reconstruction.flatten(myg, q, 2, ivars, rp)

        xi = reconstruction.flatten_multid(myg, q, xi_x, xi_y, ivars)
    else:
        xi = 1.0


    # monotonized central differences in x-direction
    tm_limit = tc.timer("limiting")
    tm_limit.begin()

    limiter = rp.get_param("compressible.limiter")

    ldx = myg.scratch_array(nvar=ivars.nvar)
    ldy = myg.scratch_array(nvar=ivars.nvar)

    for n in range(ivars.nvar):
        ldx[:,:,n] = xi*reconstruction.limit(q[:,:,n], myg, 1, limiter)
        ldy[:,:,n] = xi*reconstruction.limit(q[:,:,n], myg, 2, limiter)        

    tm_limit.end()


    #=========================================================================
    # x-direction
    #=========================================================================

    # left and right primitive variable states
    tm_states = tc.timer("interfaceStates")
    tm_states.begin()

    V_l = myg.scratch_array(ivars.nvar)
    V_r = myg.scratch_array(ivars.nvar)

    for n in range(ivars.nvar):
        V_l.ip(1, n=n, buf=2)[:,:] = q.v(n=n, buf=2) + 0.5*ldx.v(n=n, buf=2)
        V_r.v(n=n, buf=2)[:,:] = q.v(n=n, buf=2) - 0.5*ldx.v(n=n, buf=2)

    tm_states.end()


    # transform interface states back into conserved variables
    U_xl = comp.prim_to_cons(V_l, gamma, ivars, myg)
    U_xr = comp.prim_to_cons(V_r, gamma, ivars, myg)


    #=========================================================================
    # y-direction
    #=========================================================================

    # left and right primitive variable states
    tm_states.begin()

    for n in range(ivars.nvar):
        V_l.jp(1, n=n, buf=2)[:,:] = q.v(n=n, buf=2) + 0.5*ldy.v(n=n, buf=2)
        V_r.v(n=n, buf=2)[:,:] = q.v(n=n, buf=2) - 0.5*ldy.v(n=n, buf=2)

    tm_states.end()


    # transform interface states back into conserved variables
    U_yl = comp.prim_to_cons(V_l, gamma, ivars, myg)
    U_yr = comp.prim_to_cons(V_r, gamma, ivars, myg)


    #=========================================================================
    # construct the fluxes normal to the interfaces
    #=========================================================================
    tm_riem = tc.timer("Riemann")
    tm_riem.begin()

    riemann = rp.get_param("compressible.riemann")

    if riemann == "HLLC":
        riemannFunc = interface_f.riemann_hllc
    elif riemann == "CGF":
        riemannFunc = interface_f.riemann_cgf
    else:
        msg.fail("ERROR: Riemann solver undefined")

    _fx = riemannFunc(1, myg.qx, myg.qy, myg.ng,
                      ivars.nvar, ivars.idens, ivars.ixmom, ivars.iymom, ivars.iener,
                      solid.xl, solid.xr,
                      gamma, U_xl, U_xr)

    _fy = riemannFunc(2, myg.qx, myg.qy, myg.ng,
                      ivars.nvar, ivars.idens, ivars.ixmom, ivars.iymom, ivars.iener,
                      solid.yl, solid.yr,
                      gamma, U_yl, U_yr)

    F_x = ai.ArrayIndexer(d=_fx, grid=myg)
    F_y = ai.ArrayIndexer(d=_fy, grid=myg)

    tm_riem.end()

    #=========================================================================
    # apply artificial viscosity
    #=========================================================================
    cvisc = rp.get_param("compressible.cvisc")

    _ax, _ay = interface_f.artificial_viscosity(
        myg.qx, myg.qy, myg.ng, myg.dx, myg.dy,
        cvisc, q.v(n=ivars.iu, buf=myg.ng), q.v(n=ivars.iv, buf=myg.ng))

    avisco_x = ai.ArrayIndexer(d=_ax, grid=myg)
    avisco_y = ai.ArrayIndexer(d=_ay, grid=myg)


    b = (2,1)

    for n in range(ivars.nvar):
        # F_x = F_x + avisco_x * (U(i-1,j) - U(i,j))
        var = my_data.get_var_by_index(n)

        F_x.v(buf=b, n=n)[:,:] += \
            avisco_x.v(buf=b)*(var.ip(-1, buf=b) - var.v(buf=b))

        # F_y = F_y + avisco_y * (U(i,j-1) - U(i,j))
        F_y.v(buf=b, n=n)[:,:] += \
            avisco_y.v(buf=b)*(var.jp(-1, buf=b) - var.v(buf=b))

    tm_flux.end()

    return F_x, F_y