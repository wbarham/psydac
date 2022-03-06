# -*- coding: UTF-8 -*-

import pytest
import time
import numpy as np
from mpi4py import MPI
from sympy  import pi, sin, cos, Tuple, Matrix

from scipy.sparse.linalg import spsolve, inv

from sympde.calculus      import grad, dot, curl, cross
from sympde.calculus      import minus, plus
from sympde.topology      import VectorFunctionSpace
from sympde.topology      import elements_of
from sympde.topology      import NormalVector
from sympde.topology      import Square
from sympde.topology      import IdentityMapping, PolarMapping
from sympde.expr.expr     import LinearForm, BilinearForm
from sympde.expr.expr     import integral
from sympde.expr.expr     import Norm
from sympde.expr.equation import find, EssentialBC

from psydac.api.discretization       import discretize
from psydac.api.tests.build_domain   import build_pretzel
from psydac.fem.basic                import FemField
from psydac.linalg.iterative_solvers import *
from psydac.api.settings             import PSYDAC_BACKEND_GPYCCEL
from psydac.feec.pull_push           import pull_2d_hcurl
from psydac.linalg.utilities         import array_to_stencil

#==============================================================================
def run_maxwell_2d(uex, f, alpha, domain, ncells, degree, k=None, kappa=None, comm=None):

    #+++++++++++++++++++++++++++++++
    # 1. Abstract model
    #+++++++++++++++++++++++++++++++

    V  = VectorFunctionSpace('V', domain, kind='hcurl')

    u, v, F  = elements_of(V, names='u, v, F')
    nn       = NormalVector('nn')

    error   = Matrix([F[0]-uex[0],F[1]-uex[1]])

    I        = domain.interfaces
    boundary = domain.boundary

    kappa   = 10*2**10
    k       = 1

    jump = lambda w:plus(w)-minus(w)
    avr  = lambda w:(plus(w) + minus(w))/2

    expr1_I  =  cross(nn, jump(v))*curl(avr(u))\
               +k*cross(nn, jump(u))*curl(avr(v))\
               +kappa*cross(nn, jump(u))*cross(nn, jump(v))

    expr1   = curl(u)*curl(v) + alpha*dot(u,v)
    expr1_b = -cross(nn, v) * curl(u) -k*cross(nn, u)*curl(v)  + kappa*cross(nn, u)*cross(nn, v)

    expr2   = dot(f,v)
    expr2_b = -k*cross(nn, uex)*curl(v) + kappa * cross(nn, uex) * cross(nn, v)

    # Bilinear form a: V x V --> R
    a      = BilinearForm((u,v),  integral(domain, expr1) + integral(I, expr1_I) + integral(boundary, expr1_b))

    # Linear form l: V --> R
    l      = LinearForm(v, integral(domain, expr2) + integral(boundary, expr2_b))

    equation = find(u, forall=v, lhs=a(u,v), rhs=l(v))

    l2norm = Norm(error, domain, kind='l2')
    #+++++++++++++++++++++++++++++++
    # 2. Discretization
    #+++++++++++++++++++++++++++++++

    domain_h = discretize(domain, ncells=ncells, comm=comm)
    Vh       = discretize(V, domain_h, degree=degree, basis='M')

    equation_h = discretize(equation, domain_h, [Vh, Vh], backend=PSYDAC_BACKEND_GPYCCEL)
    l2norm_h   = discretize(l2norm, domain_h, Vh)

    equation_h.set_solver('minres', tol=1e-8, info=True, maxiter=100000)

    timing   = {}
    t0       = time.time()
    A        = equation_h.lhs.assemble().tosparse().tocsr()
    b        = equation_h.rhs.assemble().toarray()
    x        = spsolve(A,b)
    x        = array_to_stencil(x, Vh.vector_space)
    uh       = FemField(Vh, x)
    info     = 0
#    uh, info = equation_h.solve()
    t1       = time.time()
    timing['solution'] = t1-t0

    t0 = time.time()
    l2_error = l2norm_h.assemble(F=uh)
    t1       = time.time()
    timing['diagnostics'] = t1-t0

    return uh, info, timing, l2_error

if __name__ == '__main__':

    from collections                               import OrderedDict
    from sympy                                     import lambdify
    from psydac.api.tests.build_domain             import build_pretzel
    from psydac.feec.multipatch.plotting_utilities import get_plotting_grid, get_grid_vals
    from psydac.feec.multipatch.plotting_utilities import get_patch_knots_gridlines, my_small_plot

#    domain    = build_pretzel()

    A = Square('A',bounds1=(0.5, 1.), bounds2=(0, np.pi/2))
    B = Square('B',bounds1=(0.5, 1.), bounds2=(np.pi/2, np.pi))
    C = Square('C',bounds1=(0.5, 1.), bounds2=(np.pi, 1.5*np.pi))
    D = Square('D',bounds1=(0.5, 1.), bounds2=(1.5*np.pi, 2*np.pi))

    mapping_1 = PolarMapping('M1',2, c1= 0., c2= 0., rmin = 0., rmax=1.)
    mapping_2 = PolarMapping('M2',2, c1= 0., c2= 0., rmin = 0., rmax=1.)
    mapping_3 = PolarMapping('M3',2, c1= 0., c2= 0., rmin = 0., rmax=1.)
    mapping_4 = PolarMapping('M4',2, c1= 0., c2= 0., rmin = 0., rmax=1.)

    D1     = mapping_1(A)
    D2     = mapping_2(B)
    D3     = mapping_3(C)
    D4     = mapping_4(D)

    domain1 = D1.join(D2, name = 'domain1',
                bnd_minus = D1.get_boundary(axis=1, ext=1),
                bnd_plus  = D2.get_boundary(axis=1, ext=-1))

    domain2 = domain1.join(D3, name='domain2',
                    bnd_minus = D2.get_boundary(axis=1, ext=1),
                    bnd_plus  = D3.get_boundary(axis=1, ext=-1))

    domain = domain2.join(D4, name='domain',
                    bnd_minus = D3.get_boundary(axis=1, ext=1),
                    bnd_plus  = D4.get_boundary(axis=1, ext=-1))

    domain = domain.join(domain, name='domain',
                        bnd_minus = D4.get_boundary(axis=1, ext=1),
                        bnd_plus  = D1.get_boundary(axis=1, ext=-1))

    x,y       = domain.coordinates
    omega = 1.5
    alpha = -omega**2
    Eex   = Tuple(sin(pi*y), sin(pi*x)*cos(pi*y))
    f     = Tuple(alpha*sin(pi*y) - pi**2*sin(pi*y)*cos(pi*x) + pi**2*sin(pi*y),
                  alpha*sin(pi*x)*cos(pi*y) + pi**2*sin(pi*x)*cos(pi*y))


    interiors = domain.interior.args
    ne        = {}
    ne[interiors[0].name] = [2**4,2**4]
    ne[interiors[1].name] = [2**4,2**4]
    ne[interiors[2].name] = [2**4,2**4]
    ne[interiors[3].name] = [2**5,2**5]
    degree = [2,2]

    Eh, info, timing, l2_error = run_maxwell_2d(Eex, f, alpha, domain, ncells=ne, degree=degree)

    # ...
    print( '> Grid          :: {}'.format(ne) )
    print( '> Degree        :: [{p1},{p2}]'  .format( p1=degree[0], p2=degree[1] ) )
    print( '> CG info       :: ',info )
    print( '> L2 error      :: {:.2e}'.format( l2_error ) )
    print( '' )
    print( '> Solution time :: {:.2e}'.format( timing['solution'] ) )
    print( '> Evaluat. time :: {:.2e}'.format( timing['diagnostics'] ) )
    N = 20

    mappings = OrderedDict([(P.logical_domain, P.mapping) for P in domain.interior])
    mappings_list = list(mappings.values())

    Eex_x   = lambdify(domain.coordinates, Eex[0])
    Eex_y   = lambdify(domain.coordinates, Eex[1])
    Eex_log = [pull_2d_hcurl([Eex_x,Eex_y], f) for f in mappings_list]

    etas, xx, yy         = get_plotting_grid(mappings, N=20)

    gridlines_x1_0, gridlines_x2_0 = get_patch_knots_gridlines(Eh.space, N, mappings, plotted_patch=0)
    gridlines_x1_1, gridlines_x2_1 = get_patch_knots_gridlines(Eh.space, N, mappings, plotted_patch=1)
    gridlines_x1_2, gridlines_x2_2 = get_patch_knots_gridlines(Eh.space, N, mappings, plotted_patch=2)
    gridlines_x1_3, gridlines_x2_3 = get_patch_knots_gridlines(Eh.space, N, mappings, plotted_patch=3)

    grid_vals_hcurl      = lambda v: get_grid_vals(v, etas, mappings_list, space_kind='hcurl')

    Eh_x_vals, Eh_y_vals = grid_vals_hcurl(Eh)
    E_x_vals, E_y_vals   = grid_vals_hcurl(Eex_log)

    E_x_err              = [(u1 - u2) for u1, u2 in zip(E_x_vals, Eh_x_vals)]
    E_y_err              = [(u1 - u2) for u1, u2 in zip(E_y_vals, Eh_y_vals)]

    my_small_plot(
        title=r'approximation of solution $u$, $x$ component',
        vals=[E_x_vals, Eh_x_vals, E_x_err],
        titles=[r'$u^{ex}_x(x,y)$', r'$u^h_x(x,y)$', r'$|(u^{ex}-u^h)_x(x,y)|$'],
        xx=xx,
        yy=yy,
        gridlines_x1=[gridlines_x1_0,gridlines_x1_1, gridlines_x1_2, gridlines_x1_3],
        gridlines_x2=[gridlines_x2_0,gridlines_x2_1, gridlines_x2_2, gridlines_x2_3],
    )

    my_small_plot(
        title=r'approximation of solution $u$, $y$ component',
        vals=[E_y_vals, Eh_y_vals, E_y_err],
        titles=[r'$u^{ex}_y(x,y)$', r'$u^h_y(x,y)$', r'$|(u^{ex}-u^h)_y(x,y)|$'],
        xx=xx,
        yy=yy,
        gridlines_x1=[gridlines_x1_0,gridlines_x1_1, gridlines_x1_2, gridlines_x1_3],
        gridlines_x2=[gridlines_x2_0,gridlines_x2_1, gridlines_x2_2, gridlines_x2_3],
    )
