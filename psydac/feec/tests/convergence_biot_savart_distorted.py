import logging
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sympy





from psydac.api.discretization import discretize
from psydac.api.feec import DiscreteDerham
from psydac.api.fem  import DiscreteLinearForm
from psydac.fem.basic          import FemField
from psydac.api.postprocessing import OutputManager, PostProcessManager
from psydac.feec.global_projectors import Projector_H1, Projector_Hdiv
from psydac.feec.tests.magnetostatic_pbm_annulus import solve_magnetostatic_pbm_J_direct_with_bc
from psydac.fem.basic import FemField
from psydac.linalg.utilities import array_to_psydac
from psydac.linalg.stencil import StencilVector
from sympde.expr import LinearForm, integral
from sympde.expr.expr import Norm
from sympde.topology  import Derham, Square
from sympde.topology.domain import Domain, Union

import sympde.topology as top

from psydac.feec.tests.test_magnetostatic_pbm_annulus import (DistortedPolarMapping, 
                                                              _create_distorted_annulus_and_derham)

def l2_error_biot_savart_distorted(N, p):
    """
    Computes L2 error of solution of the Biot-Savart problem with curve integral constraint in 2D
    (see test_magnetostatic_pbm_annulus.py for details) for the distorted annulus domain 
    """
    logger = logging.getLogger("test_magnetostatic_pbm_annuluslike")
    domain, derham = _create_distorted_annulus_and_derham()
    ncells = [N,N//2]
    domain_h = discretize(domain, ncells=ncells, periodic=[False, True])
    derham_h = discretize(derham, domain_h, degree=[p,p])
    assert isinstance(derham_h, DiscreteDerham)

    psi = lambda alpha, theta : 2*alpha if alpha <= 0.5 else 1.0
    h1_proj = Projector_H1(derham_h.V0)
    psi_h = h1_proj(psi) 
    x, y = sympy.symbols(names='x, y')
    J = 1e-10

    does_plot_psi = True
    if does_plot_psi:
        output_manager = OutputManager('magnetostatic_V0.yml',
                                             'psi_h.h5')
        output_manager.add_spaces(V0=derham_h.V0)
        output_manager.export_space_info()
        output_manager.set_static()
        output_manager.export_fields(psi_h=psi_h)
        post_processor = PostProcessManager(domain=domain,
                                            space_file='magnetostatic_V0.yml',
                                            fields_file='psi_h.h5')
        post_processor.export_to_vtk('psi_h_vtk', npts_per_cell=5, fields='psi_h')

    # Compute right hand side of the curve integral constraint
    logical_domain_gamma = Square(name='logical_domain_gamma', bounds1=(0,0.5), bounds2=(0,2*np.pi))
    boundary_logical_domain_gamma = Union(logical_domain_gamma.get_boundary(axis=0, ext=-1),
                                    logical_domain_gamma.get_boundary(axis=0, ext=1))
    logical_domain_gamma = Domain(name='logical_domain_gamma',
                            interiors=logical_domain_gamma.interior,
                            boundaries=boundary_logical_domain_gamma,
                            dim=2)
    distorted_polar_mapping = DistortedPolarMapping(name='polar_mapping', dim=2)
    omega_gamma = distorted_polar_mapping(logical_domain_gamma)
    derham_gamma = Derham(domain=omega_gamma, sequence=['H1', 'Hdiv', 'L2'])
    omega_gamma_h = discretize(omega_gamma, ncells=[N//2,N//2], periodic=[False, True])
    derham_gamma_h = discretize(derham_gamma, omega_gamma_h, degree=[p,p])
    h1_proj_gamma = Projector_H1(derham_gamma_h.V0)
    assert isinstance(derham_h, DiscreteDerham)

    sigma, tau = top.elements_of(derham_gamma.V0, names='sigma tau')
    inner_prod_J = LinearForm(tau, integral(omega_gamma, J*tau))
    inner_prod_J_h = discretize(inner_prod_J, omega_gamma_h, space=derham_gamma_h.V0)
    assert isinstance(inner_prod_J_h, DiscreteLinearForm)
    inner_prod_J_h_stencil = inner_prod_J_h.assemble()
    # Try changing this to the evaluation using the dicrete linear form directly
    assert isinstance(inner_prod_J_h_stencil, StencilVector)
    inner_prod_J_h_vec = inner_prod_J_h_stencil.toarray()
    logger.debug("np.linalg.norm(inner_prod_J_h_vec):%s\n", np.linalg.norm(inner_prod_J_h_vec))

    psi_h_gamma = h1_proj_gamma(psi)
    psi_h_gamma_coeffs = psi_h_gamma.coeffs.toarray()
    c_0 = -4*np.pi
    rhs_curve_integral = c_0 + np.dot(inner_prod_J_h_vec, psi_h_gamma_coeffs)
    logger.debug("rhs_curve_integral + 4*np.pi:%s\n", rhs_curve_integral + 4*np.pi)

    h_div_projector = Projector_Hdiv(derham_h.V1)
    B_exact_1 = lambda x,y: -2*y/(x**2 + y**2) 
    B_exact_2 = lambda x,y: 2*x/(x**2 + y**2)
    B_exact = (B_exact_1, B_exact_2)
    P0, P1, P2 = derham_h.projectors()
    boundary_data = P1(B_exact) 


    B_h_coeffs_arr = solve_magnetostatic_pbm_J_direct_with_bc(J, psi_h=psi_h, rhs_curve_integral=rhs_curve_integral,
                                                     boundary_data=boundary_data,
                                                     derham=derham,
                                                     derham_h=derham_h,
                                                     domain_h=domain_h)
    
    B_h_coeffs = array_to_psydac(B_h_coeffs_arr, derham_h.V1.vector_space)
    B_h = FemField(derham_h.V1, coeffs=B_h_coeffs)

    does_plot = True
    if does_plot:
        output_manager = OutputManager('spaces_magnetostatic_distorted_annulus.yml', 
                                       'fields_magnetostatic_distorted_annulus.h5')
        output_manager.add_spaces(V1=derham_h.V1)
        output_manager.export_space_info()
        output_manager.set_static()
        output_manager.export_fields(B_h=B_h, B_exact=boundary_data)
        post_processor = PostProcessManager(domain=domain, 
                                            space_file='spaces_magnetostatic_distorted_annulus.yml',
                                            fields_file='fields_magnetostatic_distorted_annulus.h5')
        post_processor.export_to_vtk('magnetostatic_pbm_distorted_annulus_vtk', npts_per_cell=3,
                                        fields=("B_h", "B_exact"))


    # eval_grid = [np.array([0.25, 0.5, 0.75]), np.array([np.pi/2, np.pi])]
    # V1h = derham_h.V1
    # assert isinstance(V1h, VectorFemSpace)
    # B_h_eval = V1h.eval_fields(eval_grid, B_h)
    # B_exact_logical = pull_2d_hdiv(B_exact, distorted_polar_mapping.get_callable_mapping())
    # print(B_h_eval)
    # assert abs( B_h_eval[0][0][0,1] - B_exact_logical[0](eval_grid[0][0], eval_grid[1][1])) < 0.01, f"B_h_eval[0][0][0,1] - B_exact[0](eval_grid[0,0], eval_grid[1,1]):{B_h_eval[0][0][0,1] - B_exact_logical[0](eval_grid[0][0], eval_grid[1][1])}"
    # assert abs(B_h_eval[0][1][0,1] - B_exact_logical[1](eval_grid[0][0], eval_grid[1][1])) < 0.01, f"B_h_eval[0][1][0,1] - B_exact[1](eval_grid[0,0], eval_grid[1,1]):{B_h_eval[0][1][0,1] - B_exact_logical[1](eval_grid[0][0], eval_grid[1][1])}"
    # assert abs( B_h_eval[0][1][2,0] - B_exact_logical[1](eval_grid[0][2], eval_grid[1][0])) < 0.01, f"B_h_eval[0][0][2,0] - B_exact[1](eval_grid[0,2], eval_grid[1,0]):{B_h_eval[0][1][2,0] - B_exact_logical[1](eval_grid[0][2], eval_grid[1][0])}"

    x, y = domain.coordinates
    B_ex = sympy.Tuple(2.0/(x**2 + y**2)*(-y), 2.0/(x**2 + y**2)*x)
    v, _ = top.elements_of(derham.V1, names='v, _')
    error = sympy.Matrix([v[0]-B_ex[0], v[1]-B_ex[1]])
    l2_error_symbolic = Norm(error, domain)
    l2_error_h_symbolic = discretize(l2_error_symbolic, domain_h, derham_h.V1)
    l2_error = l2_error_h_symbolic.assemble(v=B_h)

    return l2_error


if __name__ == '__main__':
    computes_l2_errors = True
    if computes_l2_errors:
        l2_error_data = {"n_cells": np.array([8,12,16,24,32,48,64]), "l2_error": np.zeros(7)}
        for i,N in enumerate([8,12,16,24,32,48,64]):
            l2_error_data['l2_error'][i] = l2_error_biot_savart_distorted(N, 3)
            
        np.savetxt('l2_error_data/biot_savart_distorted/degree3/n_cells.csv',
                   l2_error_data['n_cells'], delimiter='\t')
        np.savetxt('l2_error_data/biot_savart_distorted/degree3/l2_error.csv',
                   l2_error_data['l2_error'], delimiter='\t')


    l2_error_data = {"n_cells": np.array([8,12,16,24,32,48,64]), "l2_error": np.zeros(7)}
    # with open('l2_error_data/biot_savart_distorted.pkl', 'rb') as file:
    #     l2_error_data = pickle.load(file)
    
    
    n_cells = np.loadtxt('l2_error_data/biot_savart_distorted/degree3/n_cells.csv')
    l2_error = np.loadtxt('l2_error_data/biot_savart_distorted/degree3/l2_error.csv')

    l2_error_array = np.column_stack((n_cells, l2_error))

    l2_error_data = pd.DataFrame(data=l2_error_array, columns=['N', 'l2_error'])
    l2_error_data.to_csv('l2_error_data/biot_savart_distorted/degree3/l2_error_data.csv',
                            index=False, header=True, sep='\t')
    # l2_error_data['n_cells'] = n_cells
    # l2_error_data['l2_error'] = l2_error

    h = l2_error_data['N']**(-1.0)
    h_squared = l2_error_data['N']**(-2.0)
    h_cubed = l2_error_data['N']**(-3.0)
    plt.loglog(l2_error_data['N'], l2_error_data['l2_error'], marker='o', label='l2_error')
    plt.loglog(l2_error_data['N'], h)
    plt.loglog(l2_error_data['N'], 100*h_squared)
    plt.loglog(l2_error_data['N'], 2500*h_cubed)
    plt.legend()
    plt.show()
