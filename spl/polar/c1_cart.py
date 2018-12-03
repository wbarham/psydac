# coding: utf-8
#
# Copyright 2018 Yaman Güçlü

from spl.ddm.cart import Cart

__all__ = ['C1_Cart']

#==============================================================================
class C1_Cart( Cart ):
    """
    A new Cart() that is generated from an existing one by removing all degrees
    of freedom corresponding to i_d = 0, 1 with d being the radial dimension.

    This is used to apply a C1-correction to a tensor-product finite element
    space built on a mapping with a polar singularity.

    Parameters
    ----------
    cart : spl.ddm.Cart
        MPI decomposition of a logical grid with Cartesian topology.

    radial_dim : int
        'Radial' dimension where degrees of freedom should be removed.

    """
    def __init__( self, cart, radial_dim=0 ):

        assert isinstance( cart, Cart )
        assert isinstance( radial_dim, int )
        assert 0 <= radial_dim < cart.ndim
        assert cart.ndim >= 2
        assert cart.periods[radial_dim] == False

        # Initialize in standard way
        super().__init__( cart.npts, cart.pads, cart.periods, cart.reorder, cart.comm )

        # Reduce start/end index (and number of points) in radial dimension by 2
        self._starts = tuple( (max(0,s-2) if d==radial_dim else s) for (d,s) in enumerate( self.starts ) )
        self._ends   = tuple( (      e-2  if d==radial_dim else e) for (d,e) in enumerate( self.ends   ) )
        self._npts   = tuple( (      n-2  if d==radial_dim else n) for (d,n) in enumerate( self.npts   ) )

        self._global_starts[radial_dim] -= 2
        self._global_ends  [radial_dim] -= 2

        # Make sure that we start counting from index 0
        self._global_starts[radial_dim][0] = 0

        # Recompute shape of local arrays in topology (with ghost regions)
        self._shape = tuple( e-s+1+2*p for s,e,p in zip( self._starts, self._ends, self._pads ) )
 
        # Recompute information for communicating with neighbors
        self._shift_info = {}
        for dimension in range( self._ndims ):
            for disp in [-1,1]:
                self._shift_info[ dimension, disp ] = \
                        self._compute_shift_info( dimension, disp )

        # Store "parent" cart object for later reference
        self._parent_cart = cart

    # ...
    @property
    def parent_cart( self ):
        return self._parent_cart
