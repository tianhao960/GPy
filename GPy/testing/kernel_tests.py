# Copyright (c) 2012, 2013 GPy authors (see AUTHORS.txt).
# Licensed under the BSD 3-clause license (see LICENSE.txt)

import unittest
import numpy as np
import GPy
import sys

verbose = True

class Kern_check_model(GPy.core.Model):
    """
    This is a dummy model class used as a base class for checking that the
    gradients of a given kernel are implemented correctly. It enables
    checkgrad() to be called independently on a kernel.
    """
    def __init__(self, kernel=None, dL_dK=None, X=None, X2=None):
        GPy.core.Model.__init__(self, 'kernel_test_model')
        if kernel==None:
            kernel = GPy.kern.RBF(1)
        if X is None:
            X = np.random.randn(20, kernel.input_dim)
        if dL_dK is None:
            if X2 is None:
                dL_dK = np.ones((X.shape[0], X.shape[0]))
            else:
                dL_dK = np.ones((X.shape[0], X2.shape[0]))

        self.kernel = kernel
        self.X = GPy.core.parameterization.Param('X',X)
        self.X2 = X2
        self.dL_dK = dL_dK

    def is_positive_definite(self):
        v = np.linalg.eig(self.kernel.K(self.X))[0]
        if any(v<-10*sys.float_info.epsilon):
            return False
        else:
            return True

    def log_likelihood(self):
        return np.sum(self.dL_dK*self.kernel.K(self.X, self.X2))

class Kern_check_dK_dtheta(Kern_check_model):
    """
    This class allows gradient checks for the gradient of a kernel with
    respect to parameters.
    """
    def __init__(self, kernel=None, dL_dK=None, X=None, X2=None):
        Kern_check_model.__init__(self,kernel=kernel,dL_dK=dL_dK, X=X, X2=X2)
        self.add_parameter(self.kernel)

    def parameters_changed(self):
        return self.kernel.update_gradients_full(self.dL_dK, self.X, self.X2)


class Kern_check_dKdiag_dtheta(Kern_check_model):
    """
    This class allows gradient checks of the gradient of the diagonal of a
    kernel with respect to the parameters.
    """
    def __init__(self, kernel=None, dL_dK=None, X=None):
        Kern_check_model.__init__(self,kernel=kernel,dL_dK=dL_dK, X=X, X2=None)
        self.add_parameter(self.kernel)

    def log_likelihood(self):
        return (np.diag(self.dL_dK)*self.kernel.Kdiag(self.X)).sum()

    def parameters_changed(self):
        self.kernel.update_gradients_diag(np.diag(self.dL_dK), self.X)

class Kern_check_dK_dX(Kern_check_model):
    """This class allows gradient checks for the gradient of a kernel with respect to X. """
    def __init__(self, kernel=None, dL_dK=None, X=None, X2=None):
        Kern_check_model.__init__(self,kernel=kernel,dL_dK=dL_dK, X=X, X2=X2)
        self.add_parameter(self.X)

    def parameters_changed(self):
        self.X.gradient =  self.kernel.gradients_X(self.dL_dK, self.X, self.X2)

class Kern_check_dKdiag_dX(Kern_check_dK_dX):
    """This class allows gradient checks for the gradient of a kernel diagonal with respect to X. """
    def __init__(self, kernel=None, dL_dK=None, X=None, X2=None):
        Kern_check_dK_dX.__init__(self,kernel=kernel,dL_dK=dL_dK, X=X, X2=None)

    def log_likelihood(self):
        return (np.diag(self.dL_dK)*self.kernel.Kdiag(self.X)).sum()

    def parameters_changed(self):
        self.X.gradient =  self.kernel.gradients_X_diag(self.dL_dK, self.X)



def kern_test(kern, X=None, X2=None, output_ind=None, verbose=False):
    """
    This function runs on kernels to check the correctness of their
    implementation. It checks that the covariance function is positive definite
    for a randomly generated data set.

    :param kern: the kernel to be tested.
    :type kern: GPy.kern.Kernpart
    :param X: X input values to test the covariance function.
    :type X: ndarray
    :param X2: X2 input values to test the covariance function.
    :type X2: ndarray

    """
    pass_checks = True
    if X==None:
        X = np.random.randn(10, kern.input_dim)
        if output_ind is not None:
            X[:, output_ind] = np.random.randint(kern.output_dim, X.shape[0])
    if X2==None:
        X2 = np.random.randn(20, kern.input_dim)
        if output_ind is not None:
            X2[:, output_ind] = np.random.randint(kern.output_dim, X2.shape[0])

    if verbose:
        print("Checking covariance function is positive definite.")
    result = Kern_check_model(kern, X=X).is_positive_definite()
    if result and verbose:
        print("Check passed.")
    if not result:
        print("Positive definite check failed for " + kern.name + " covariance function.")
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of K(X, X) wrt theta.")
    result = Kern_check_dK_dtheta(kern, X=X, X2=None).checkgrad(verbose=verbose)
    if result and verbose:
        print("Check passed.")
    if not result:
        print("Gradient of K(X, X) wrt theta failed for " + kern.name + " covariance function. Gradient values as follows:")
        Kern_check_dK_dtheta(kern, X=X, X2=None).checkgrad(verbose=True)
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of K(X, X2) wrt theta.")
    result = Kern_check_dK_dtheta(kern, X=X, X2=X2).checkgrad(verbose=verbose)
    if result and verbose:
        print("Check passed.")
    if not result:
        print("Gradient of K(X, X) wrt theta failed for " + kern.name + " covariance function. Gradient values as follows:")
        Kern_check_dK_dtheta(kern, X=X, X2=X2).checkgrad(verbose=True)
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of Kdiag(X) wrt theta.")
    result = Kern_check_dKdiag_dtheta(kern, X=X).checkgrad(verbose=verbose)
    if result and verbose:
        print("Check passed.")
    if not result:
        print("Gradient of Kdiag(X) wrt theta failed for " + kern.name + " covariance function. Gradient values as follows:")
        Kern_check_dKdiag_dtheta(kern, X=X).checkgrad(verbose=True)
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of K(X, X) wrt X.")
    try:
        result = Kern_check_dK_dX(kern, X=X, X2=None).checkgrad(verbose=verbose)
    except NotImplementedError:
        result=True
        if verbose:
            print("gradients_X not implemented for " + kern.name)
    if result and verbose:
        print("Check passed.")
    if not result:
        print("Gradient of K(X, X) wrt X failed for " + kern.name + " covariance function. Gradient values as follows:")
        Kern_check_dK_dX(kern, X=X, X2=None).checkgrad(verbose=True)
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of K(X, X2) wrt X.")
    try:
        result = Kern_check_dK_dX(kern, X=X, X2=X2).checkgrad(verbose=verbose)
    except NotImplementedError:
        result=True
        if verbose:
            print("gradients_X not implemented for " + kern.name)
    if result and verbose:
        print("Check passed.")
    if not result:
        print("Gradient of K(X, X) wrt X failed for " + kern.name + " covariance function. Gradient values as follows:")
        Kern_check_dK_dX(kern, X=X, X2=X2).checkgrad(verbose=True)
        pass_checks = False
        return False

    if verbose:
        print("Checking gradients of Kdiag(X) wrt X.")
    try:
        result = Kern_check_dKdiag_dX(kern, X=X).checkgrad(verbose=verbose)
    except NotImplementedError:
        result=True
        if verbose:
            print("gradients_X not implemented for " + kern.name)
    if result and verbose:
        print("Check passed.")
    if not result:
        print("Gradient of Kdiag(X) wrt X failed for " + kern.name + " covariance function. Gradient values as follows:")
        Kern_check_dKdiag_dX(kern, X=X).checkgrad(verbose=True)
        pass_checks = False
        return False

    return pass_checks



class KernelTestsContinuous(unittest.TestCase):
    def setUp(self):
        self.X = np.random.randn(100,2)
        self.X2 = np.random.randn(110,2)

        continuous_kerns = ['RBF', 'Linear']
        self.kernclasses = [getattr(GPy.kern, s) for s in continuous_kerns]

    def test_Matern32(self):
        k = GPy.kern.Matern32(2)
        self.assertTrue(kern_test(k, X=self.X, X2=self.X2, verbose=verbose))

    def test_Matern52(self):
        k = GPy.kern.Matern52(2)
        self.assertTrue(kern_test(k, X=self.X, X2=self.X2, verbose=verbose))

    #TODO: turn off grad checkingwrt X for indexed kernels liek coregionalize




if __name__ == "__main__":
    print "Running unit tests, please be (very) patient..."
    unittest.main()
