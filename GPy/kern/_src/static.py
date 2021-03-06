# Copyright (c) 2012, GPy authors (see AUTHORS.txt).
# Licensed under the BSD 3-clause license (see LICENSE.txt)


from kern import Kern
import numpy as np
from ...core.parameterization import Param
from ...core.parameterization.transformations import Logexp
import numpy as np

class Static(Kern):
    def __init__(self, input_dim, variance, name):
        super(Static, self).__init__(input_dim, name)
        self.variance = Param('variance', variance, Logexp())
        self.add_parameters(self.variance)

    def Kdiag(self, X):
        ret = np.empty((X.shape[0],), dtype=np.float64)
        ret[:] = self.variance
        return ret

    def gradients_X(self, dL_dK, X, X2=None):
        return np.zeros(X.shape)

    def gradients_X_diag(self, dL_dKdiag, X):
        return np.zeros(X.shape)

    def gradients_Z_expectations(self, dL_dpsi1, dL_dpsi2, Z, variational_posterior):
        return np.zeros(Z.shape)

    def gradients_qX_expectations(self, dL_dpsi0, dL_dpsi1, dL_dpsi2, Z, variational_posterior):
        return np.zeros(variational_posterior.shape), np.zeros(variational_posterior.shape)

    def psi0(self, Z, variational_posterior):
        return self.Kdiag(variational_posterior.mean)

    def psi1(self, Z, variational_posterior):
        return self.K(variational_posterior.mean, Z)

    def psi2(self, Z, variational_posterior):
        K = self.K(variational_posterior.mean, Z)
        return K[:,:,None]*K[:,None,:] # NB. more efficient implementations on inherriting classes


class White(Static):
    def __init__(self, input_dim, variance=1., name='white'):
        super(White, self).__init__(input_dim, variance, name)

    def K(self, X, X2=None):
        if X2 is None:
            return np.eye(X.shape[0])*self.variance
        else:
            return np.zeros((X.shape[0], X2.shape[0]))

    def psi2(self, Z, variational_posterior):
        return np.zeros((variational_posterior.shape[0], Z.shape[0], Z.shape[0]), dtype=np.float64)

    def update_gradients_full(self, dL_dK, X, X2=None):
        self.variance.gradient = np.trace(dL_dK)

    def update_gradients_diag(self, dL_dKdiag, X):
        self.variance.gradient = dL_dKdiag.sum()

    def update_gradients_expectations(self, dL_dpsi0, dL_dpsi1, dL_dpsi2, Z, variational_posterior):
        self.variance.gradient = dL_dpsi0.sum()


class Bias(Static):
    def __init__(self, input_dim, variance=1., name='bias'):
        super(Bias, self).__init__(input_dim, variance, name)

    def K(self, X, X2=None):
        shape = (X.shape[0], X.shape[0] if X2 is None else X2.shape[0])
        ret = np.empty(shape, dtype=np.float64)
        ret[:] = self.variance
        return ret

    def update_gradients_full(self, dL_dK, X, X2=None):
        self.variance.gradient = dL_dK.sum()

    def update_gradients_diag(self, dL_dKdiag, X):
        self.variance.gradient = dL_dKdiag.sum()

    def psi2(self, Z, variational_posterior):
        ret = np.empty((variational_posterior.shape[0], Z.shape[0], Z.shape[0]), dtype=np.float64)
        ret[:] = self.variance**2
        return ret

    def update_gradients_expectations(self, dL_dpsi0, dL_dpsi1, dL_dpsi2, Z, variational_posterior):
        self.variance.gradient = dL_dpsi0.sum() + dL_dpsi1.sum() + 2.*self.variance*dL_dpsi2.sum()

