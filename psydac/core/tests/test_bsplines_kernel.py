#coding: utf-8

import pytest
import numpy as np


from psydac.core.bsplines_kernels import cell_index_p

def test_cell_index_p():
    breaks = np.array([0. , 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.])
    # i_grid = np.asarray(i_grid)
    breaks = np.ascontiguousarray(breaks, dtype=float)
    out = np.zeros_like(breaks, dtype=np.int64)
    tol = 1e-15

    # usual cases: points inside or outside domain
    for offset, expected_status in [(0, 0), (tol/2, 0), (2*tol, -1)]:
        i_grid = breaks.copy()
        i_grid[:] += offset
        status = cell_index_p(breaks, i_grid, tol, out)
        assert status == expected_status

    # limit case: code should decide wether point is in or out, not fall in infinite loop
    i_grid = breaks.copy()
    i_grid[:] += tol
    status = cell_index_p(breaks, i_grid, tol, out)
    assert status in [0,-1]
