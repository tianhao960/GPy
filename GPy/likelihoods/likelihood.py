# Copyright (c) 2012, GPy authors (see AUTHORS.txt).
# Licensed under the BSD 3-clause license (see LICENSE.txt)

import numpy as np
from scipy import stats,special
import scipy as sp
from ..util.univariate_Gaussian import std_norm_pdf,std_norm_cdf
import link_functions
from ..util.misc import chain_1, chain_2, chain_3
from scipy.integrate import quad
import warnings
from ..core.parameterization import Parameterized

class Likelihood(Parameterized):
    """
    Likelihood base class, used to defing p(y|f).

    All instances use _inverse_ link functions, which can be swapped out. It is
    expected that inherriting classes define a default inverse link function

    To use this class, inherrit and define missing functionality.

    Inherriting classes *must* implement:
       pdf_link : a bound method which turns the output of the link function into the pdf
       logpdf_link : the logarithm of the above

    To enable use with EP, inherriting classes *must* define:
       TODO: a suitable derivative function for any parameters of the class
    It is also desirable to define:
       moments_match_ep : a function to compute the EP moments If this isn't defined, the moments will be computed using 1D quadrature.

    To enable use with Laplace approximation, inherriting classes *must* define:
       Some derivative functions *AS TODO*

    For exact Gaussian inference, define *JH TODO*

    """
    def __init__(self, gp_link, name):
        super(Likelihood, self).__init__(name)
        assert isinstance(gp_link,link_functions.GPTransformation), "gp_link is not a valid GPTransformation."
        self.gp_link = gp_link
        self.log_concave = False

    def _gradients(self,partial):
        return np.zeros(0)

    def update_gradients(self, partial):
        if self.size > 0:
            raise NotImplementedError('Must be implemented for likelihoods with parameters to be optimized')

    def _preprocess_values(self,Y):
        """
        In case it is needed, this function assess the output values or makes any pertinent transformation on them.

        :param Y: observed output
        :type Y: Nx1 numpy.darray

        """
        return Y

    def log_predictive_density(self, y_test, mu_star, var_star):
        """
        Calculation of the log predictive density

        .. math:
            p(y_{*}|D) = p(y_{*}|f_{*})p(f_{*}|\mu_{*}\\sigma^{2}_{*})

        :param y_test: test observations (y_{*})
        :type y_test: (Nx1) array
        :param mu_star: predictive mean of gaussian p(f_{*}|mu_{*}, var_{*})
        :type mu_star: (Nx1) array
        :param var_star: predictive variance of gaussian p(f_{*}|mu_{*}, var_{*})
        :type var_star: (Nx1) array
        """
        assert y_test.shape==mu_star.shape
        assert y_test.shape==var_star.shape
        assert y_test.shape[1] == 1
        def integral_generator(y, m, v):
            """Generate a function which can be integrated to give p(Y*|Y) = int p(Y*|f*)p(f*|Y) df*"""
            def f(f_star):
                return self.pdf(f_star, y)*np.exp(-(1./(2*v))*np.square(m-f_star))
            return f

        scaled_p_ystar, accuracy = zip(*[quad(integral_generator(y, m, v), -np.inf, np.inf) for y, m, v in zip(y_test.flatten(), mu_star.flatten(), var_star.flatten())])
        scaled_p_ystar = np.array(scaled_p_ystar).reshape(-1,1)
        p_ystar = scaled_p_ystar/np.sqrt(2*np.pi*var_star)
        return np.log(p_ystar)

    def _moments_match_ep(self,obs,tau,v):
        """
        Calculation of moments using quadrature

        :param obs: observed output
        :param tau: cavity distribution 1st natural parameter (precision)
        :param v: cavity distribution 2nd natural paramenter (mu*precision)
        """
        #Compute first integral for zeroth moment.
        #NOTE constant np.sqrt(2*pi/tau) added at the end of the function
        mu = v/tau
        def int_1(f):
            return self.pdf(f, obs)*np.exp(-0.5*tau*np.square(mu-f))
        z_scaled, accuracy = quad(int_1, -np.inf, np.inf)

        #Compute second integral for first moment
        def int_2(f):
            return f*self.pdf(f, obs)*np.exp(-0.5*tau*np.square(mu-f))
        mean, accuracy = quad(int_2, -np.inf, np.inf)
        mean /= z_scaled

        #Compute integral for variance
        def int_3(f):
            return (f**2)*self.pdf(f, obs)*np.exp(-0.5*tau*np.square(mu-f))
        Ef2, accuracy = quad(int_3, -np.inf, np.inf)
        Ef2 /= z_scaled
        variance = Ef2 - mean**2

        #Add constant to the zeroth moment
        #NOTE: this constant is not needed in the other moments because it cancells out.
        z = z_scaled/np.sqrt(2*np.pi/tau)

        return z, mean, variance

    def _predictive_mean(self,mu,variance):
        """
        Quadrature calculation of the predictive mean: E(Y_star|Y) = E( E(Y_star|f_star, Y) )

        :param mu: mean of posterior
        :param sigma: standard deviation of posterior

        """
        def int_mean(f,m,v):
            return self._mean(f)*np.exp(-(0.5/v)*np.square(f - m))
        scaled_mean = [quad(int_mean, -np.inf, np.inf,args=(mj,s2j))[0] for mj,s2j in zip(mu,variance)]
        mean = np.array(scaled_mean)[:,None] / np.sqrt(2*np.pi*(variance))

        return mean

    def _predictive_variance(self,mu,variance,predictive_mean=None):
        """
        Numerical approximation to the predictive variance: V(Y_star)

        The following variance decomposition is used:
        V(Y_star) = E( V(Y_star|f_star) ) + V( E(Y_star|f_star) )

        :param mu: mean of posterior
        :param sigma: standard deviation of posterior
        :predictive_mean: output's predictive mean, if None _predictive_mean function will be called.

        """
        #sigma2 = sigma**2
        normalizer = np.sqrt(2*np.pi*variance)

        # E( V(Y_star|f_star) )
        def int_var(f,m,v):
            return self._variance(f)*np.exp(-(0.5/v)*np.square(f - m))
        scaled_exp_variance = [quad(int_var, -np.inf, np.inf,args=(mj,s2j))[0] for mj,s2j in zip(mu,variance)]
        exp_var = np.array(scaled_exp_variance)[:,None] / normalizer

        #V( E(Y_star|f_star) ) =  E( E(Y_star|f_star)**2 ) - E( E(Y_star|f_star) )**2

        #E( E(Y_star|f_star) )**2
        if predictive_mean is None:
            predictive_mean = self.predictive_mean(mu,variance)
        predictive_mean_sq = predictive_mean**2

        #E( E(Y_star|f_star)**2 )
        def int_pred_mean_sq(f,m,v,predictive_mean_sq):
            return self._mean(f)**2*np.exp(-(0.5/v)*np.square(f - m))
        scaled_exp_exp2 = [quad(int_pred_mean_sq, -np.inf, np.inf,args=(mj,s2j,pm2j))[0] for mj,s2j,pm2j in zip(mu,variance,predictive_mean_sq)]
        exp_exp2 = np.array(scaled_exp_exp2)[:,None] / normalizer

        var_exp = exp_exp2 - predictive_mean_sq

        # V(Y_star) = E( V(Y_star|f_star) ) + V( E(Y_star|f_star) )
        return exp_var + var_exp

    def pdf_link(self, link_f, y, extra_data=None):
        raise NotImplementedError

    def logpdf_link(self, link_f, y, extra_data=None):
        raise NotImplementedError

    def dlogpdf_dlink(self, link_f, y, extra_data=None):
        raise NotImplementedError

    def d2logpdf_dlink2(self, link_f, y, extra_data=None):
        raise NotImplementedError

    def d3logpdf_dlink3(self, link_f, y, extra_data=None):
        raise NotImplementedError

    def dlogpdf_link_dtheta(self, link_f, y, extra_data=None):
        raise NotImplementedError

    def dlogpdf_dlink_dtheta(self, link_f, y, extra_data=None):
        raise NotImplementedError

    def d2logpdf_dlink2_dtheta(self, link_f, y, extra_data=None):
        raise NotImplementedError

    def pdf(self, f, y, extra_data=None):
        """
        Evaluates the link function link(f) then computes the likelihood (pdf) using it

        .. math:
            p(y|\\lambda(f))

        :param f: latent variables f
        :type f: Nx1 array
        :param y: data
        :type y: Nx1 array
        :param extra_data: extra_data which is not used in student t distribution - not used
        :returns: likelihood evaluated for this point
        :rtype: float
        """
        link_f = self.gp_link.transf(f)
        return self.pdf_link(link_f, y, extra_data=extra_data)

    def logpdf(self, f, y, extra_data=None):
        """
        Evaluates the link function link(f) then computes the log likelihood (log pdf) using it

        .. math:
            \\log p(y|\\lambda(f))

        :param f: latent variables f
        :type f: Nx1 array
        :param y: data
        :type y: Nx1 array
        :param extra_data: extra_data which is not used in student t distribution - not used
        :returns: log likelihood evaluated for this point
        :rtype: float
        """
        link_f = self.gp_link.transf(f)
        return self.logpdf_link(link_f, y, extra_data=extra_data)

    def dlogpdf_df(self, f, y, extra_data=None):
        """
        Evaluates the link function link(f) then computes the derivative of log likelihood using it
        Uses the Faa di Bruno's formula for the chain rule

        .. math::
            \\frac{d\\log p(y|\\lambda(f))}{df} = \\frac{d\\log p(y|\\lambda(f))}{d\\lambda(f)}\\frac{d\\lambda(f)}{df}

        :param f: latent variables f
        :type f: Nx1 array
        :param y: data
        :type y: Nx1 array
        :param extra_data: extra_data which is not used in student t distribution - not used
        :returns: derivative of log likelihood evaluated for this point
        :rtype: 1xN array
        """
        link_f = self.gp_link.transf(f)
        dlogpdf_dlink = self.dlogpdf_dlink(link_f, y, extra_data=extra_data)
        dlink_df = self.gp_link.dtransf_df(f)
        return chain_1(dlogpdf_dlink, dlink_df)

    def d2logpdf_df2(self, f, y, extra_data=None):
        """
        Evaluates the link function link(f) then computes the second derivative of log likelihood using it
        Uses the Faa di Bruno's formula for the chain rule

        .. math::
            \\frac{d^{2}\\log p(y|\\lambda(f))}{df^{2}} = \\frac{d^{2}\\log p(y|\\lambda(f))}{d^{2}\\lambda(f)}\\left(\\frac{d\\lambda(f)}{df}\\right)^{2} + \\frac{d\\log p(y|\\lambda(f))}{d\\lambda(f)}\\frac{d^{2}\\lambda(f)}{df^{2}}

        :param f: latent variables f
        :type f: Nx1 array
        :param y: data
        :type y: Nx1 array
        :param extra_data: extra_data which is not used in student t distribution - not used
        :returns: second derivative of log likelihood evaluated for this point (diagonal only)
        :rtype: 1xN array
        """
        link_f = self.gp_link.transf(f)
        d2logpdf_dlink2 = self.d2logpdf_dlink2(link_f, y, extra_data=extra_data)
        dlink_df = self.gp_link.dtransf_df(f)
        dlogpdf_dlink = self.dlogpdf_dlink(link_f, y, extra_data=extra_data)
        d2link_df2 = self.gp_link.d2transf_df2(f)
        return chain_2(d2logpdf_dlink2, dlink_df, dlogpdf_dlink, d2link_df2)

    def d3logpdf_df3(self, f, y, extra_data=None):
        """
        Evaluates the link function link(f) then computes the third derivative of log likelihood using it
        Uses the Faa di Bruno's formula for the chain rule

        .. math::
            \\frac{d^{3}\\log p(y|\\lambda(f))}{df^{3}} = \\frac{d^{3}\\log p(y|\\lambda(f)}{d\\lambda(f)^{3}}\\left(\\frac{d\\lambda(f)}{df}\\right)^{3} + 3\\frac{d^{2}\\log p(y|\\lambda(f)}{d\\lambda(f)^{2}}\\frac{d\\lambda(f)}{df}\\frac{d^{2}\\lambda(f)}{df^{2}} + \\frac{d\\log p(y|\\lambda(f)}{d\\lambda(f)}\\frac{d^{3}\\lambda(f)}{df^{3}}

        :param f: latent variables f
        :type f: Nx1 array
        :param y: data
        :type y: Nx1 array
        :param extra_data: extra_data which is not used in student t distribution - not used
        :returns: third derivative of log likelihood evaluated for this point
        :rtype: float
        """
        link_f = self.gp_link.transf(f)
        d3logpdf_dlink3 = self.d3logpdf_dlink3(link_f, y, extra_data=extra_data)
        dlink_df = self.gp_link.dtransf_df(f)
        d2logpdf_dlink2 = self.d2logpdf_dlink2(link_f, y, extra_data=extra_data)
        d2link_df2 = self.gp_link.d2transf_df2(f)
        dlogpdf_dlink = self.dlogpdf_dlink(link_f, y, extra_data=extra_data)
        d3link_df3 = self.gp_link.d3transf_df3(f)
        return chain_3(d3logpdf_dlink3, dlink_df, d2logpdf_dlink2, d2link_df2, dlogpdf_dlink, d3link_df3)

    def dlogpdf_dtheta(self, f, y, extra_data=None):
        """
        TODO: Doc strings
        """
        if self.size > 0:
            link_f = self.gp_link.transf(f)
            return self.dlogpdf_link_dtheta(link_f, y, extra_data=extra_data)
        else:
            #Is no parameters so return an empty array for its derivatives
            return np.zeros([1, 0])

    def dlogpdf_df_dtheta(self, f, y, extra_data=None):
        """
        TODO: Doc strings
        """
        if self.size > 0:
            link_f = self.gp_link.transf(f)
            dlink_df = self.gp_link.dtransf_df(f)
            dlogpdf_dlink_dtheta = self.dlogpdf_dlink_dtheta(link_f, y, extra_data=extra_data)
            return chain_1(dlogpdf_dlink_dtheta, dlink_df)
        else:
            #Is no parameters so return an empty array for its derivatives
            return np.zeros([f.shape[0], 0])

    def d2logpdf_df2_dtheta(self, f, y, extra_data=None):
        """
        TODO: Doc strings
        """
        if self.size > 0:
            link_f = self.gp_link.transf(f)
            dlink_df = self.gp_link.dtransf_df(f)
            d2link_df2 = self.gp_link.d2transf_df2(f)
            d2logpdf_dlink2_dtheta = self.d2logpdf_dlink2_dtheta(link_f, y, extra_data=extra_data)
            dlogpdf_dlink_dtheta = self.dlogpdf_dlink_dtheta(link_f, y, extra_data=extra_data)
            return chain_2(d2logpdf_dlink2_dtheta, dlink_df, dlogpdf_dlink_dtheta, d2link_df2)
        else:
            #Is no parameters so return an empty array for its derivatives
            return np.zeros([f.shape[0], 0])

    def _laplace_gradients(self, f, y, extra_data=None):
        dlogpdf_dtheta = self.dlogpdf_dtheta(f, y, extra_data=extra_data)
        dlogpdf_df_dtheta = self.dlogpdf_df_dtheta(f, y, extra_data=extra_data)
        d2logpdf_df2_dtheta = self.d2logpdf_df2_dtheta(f, y, extra_data=extra_data)

        #Parameters are stacked vertically. Must be listed in same order as 'get_param_names'
        # ensure we have gradients for every parameter we want to optimize
        try:
            assert len(dlogpdf_dtheta) == self.size #1 x num_param array
            assert dlogpdf_df_dtheta.shape[1] == self.size #f x num_param matrix
            assert d2logpdf_df2_dtheta.shape[1] == self.size #f x num_param matrix
        except Exception as e:
            import ipdb; ipdb.set_trace()  # XXX BREAKPOINT

        return dlogpdf_dtheta, dlogpdf_df_dtheta, d2logpdf_df2_dtheta

    def predictive_values(self, mu, var, full_cov=False, sampling=True, num_samples=10000):
        """
        Compute  mean, variance and conficence interval (percentiles 5 and 95) of the  prediction.

        :param mu: mean of the latent variable, f, of posterior
        :param var: variance of the latent variable, f, of posterior
        :param full_cov: whether to use the full covariance or just the diagonal
        :type full_cov: Boolean
        :param num_samples: number of samples to use in computing quantiles and
                            possibly mean variance
        :type num_samples: integer
        :param sampling: Whether to use samples for mean and variances anyway
        :type sampling: Boolean

        """

        if sampling:
            #Get gp_samples f* using posterior mean and variance
            if not full_cov:
                gp_samples = np.random.multivariate_normal(mu.flatten(), np.diag(var.flatten()),
                                                            size=num_samples).T
            else:
                gp_samples = np.random.multivariate_normal(mu.flatten(), var,
                                                               size=num_samples).T
            #Push gp samples (f*) through likelihood to give p(y*|f*)
            samples = self.samples(gp_samples)
            axis=-1

            #Calculate mean, variance and precentiles from samples
            print "WARNING: Using sampling to calculate mean, variance and predictive quantiles."
            pred_mean = np.mean(samples, axis=axis)[:,None]
            pred_var = np.var(samples, axis=axis)[:,None]
            q1 = np.percentile(samples, 2.5, axis=axis)[:,None]
            q3 = np.percentile(samples, 97.5, axis=axis)[:,None]

        else:

            pred_mean = self.predictive_mean(mu, var)
            pred_var = self.predictive_variance(mu, var, pred_mean)
            print "WARNING: Predictive quantiles are only computed when sampling."
            q1 = np.repeat(np.nan,pred_mean.size)[:,None]
            q3 = q1.copy()

        return pred_mean, pred_var, q1, q3

    def samples(self, gp):
        """
        Returns a set of samples of observations based on a given value of the latent variable.

        :param gp: latent variable
        """
        raise NotImplementedError
