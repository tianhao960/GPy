# Copyright (c) 2012, GPy authors (see AUTHORS.txt).
# Licensed under the BSD 3-clause license (see LICENSE.txt)
"""
Core module for parameterization. 
This module implements all parameterization techniques, split up in modular bits.

HierarchyError:
raised when an error with the hierarchy occurs (circles etc.)

Observable:
Observable Pattern for patameterization


"""

from transformations import Transformation, Logexp, NegativeLogexp, Logistic, __fixed__, FIXED, UNFIXED
import numpy as np
import itertools

__updated__ = '2013-12-16'

class HierarchyError(Exception):
    """
    Gets thrown when something is wrong with the parameter hierarchy.
    """

def adjust_name_for_printing(name):
    """
    Make sure a name can be printed, alongside used as a variable name.
    """
    if name is not None:
        return name.replace(" ", "_").replace(".", "_").replace("-", "_m_").replace("+", "_p_").replace("!", "_I_").replace("**", "_xx_").replace("*", "_x_").replace("/", "_l_").replace("@",'_at_')
    return ''

class Observable(object):
    """
    Observable pattern for parameterization.
    
    This Object allows for observers to register with self and a (bound!) function
    as an observer. Every time the observable changes, it sends a notification with
    self as only argument to all its observers.
    """
    def __init__(self, *args, **kwargs):
        super(Observable, self).__init__()
        self._observer_callables_ = []
        
    def add_observer(self, observer, callble, priority=0):
        self._insert_sorted(priority, observer, callble)
    
    def remove_observer(self, observer, callble=None):
        to_remove = []
        for p, obs, clble in self._observer_callables_:
            if callble is not None:
                if (obs == observer) and (callble == clble):
                    to_remove.append((p, obs, clble))
            else:
                if obs is observer:
                    to_remove.append((p, obs, clble))
        for r in to_remove:
            self._observer_callables_.remove(r)
       
    def notify_observers(self, which=None, min_priority=None):
        """
        Notifies all observers. Which is the element, which kicked off this 
        notification loop.
        
        NOTE: notifies only observers with priority p > min_priority!
                                                    ^^^^^^^^^^^^^^^^
        
        :param which: object, which started this notification loop
        :param min_priority: only notify observers with priority > min_priority
                             if min_priority is None, notify all observers in order
        """
        if which is None:
            which = self
        if min_priority is None:
            [callble(which) for _, _, callble in self._observer_callables_]
        else:
            for p, _, callble in self._observer_callables_:
                if p <= min_priority:
                    break
                callble(which)

    def _insert_sorted(self, p, o, c):
        ins = 0
        for pr, _, _ in self._observer_callables_:
            if p > pr:
                break
            ins += 1
        self._observer_callables_.insert(ins, (p, o, c))
        
class Pickleable(object):
    """
    Make an object pickleable (See python doc 'pickling'). 
    
    This class allows for pickling support by Memento pattern.
    _getstate returns a memento of the class, which gets pickled.
    _setstate(<memento>) (re-)sets the state of the class to the memento 
    """
    #===========================================================================
    # Pickling operations
    #===========================================================================
    def pickle(self, f, protocol=-1):
        """
        :param f: either filename or open file object to write to.
                  if it is an open buffer, you have to make sure to close
                  it properly.
        :param protocol: pickling protocol to use, python-pickle for details.
        """
        import cPickle
        if isinstance(f, str):
            with open(f, 'w') as f:
                cPickle.dump(self, f, protocol)
        else:
            cPickle.dump(self, f, protocol)    
    def __getstate__(self):
        if self._has_get_set_state():
            return self._getstate()
        return self.__dict__
    def __setstate__(self, state):
        if self._has_get_set_state():
            self._setstate(state)  
            # TODO: maybe parameters_changed() here?
            return
        self.__dict__ = state
    def _has_get_set_state(self):
        return '_getstate' in vars(self.__class__) and '_setstate' in vars(self.__class__)
    def _getstate(self):
        """
        Returns the state of this class in a memento pattern.
        The state must be a list-like structure of all the fields
        this class needs to run.

        See python doc "pickling" (`__getstate__` and `__setstate__`) for details.
        """
        raise NotImplementedError, "To be able to use pickling you need to implement this method"
    def _setstate(self, state):
        """
        Set the state (memento pattern) of this class to the given state.
        Usually this is just the counterpart to _getstate, such that
        an object is a copy of another when calling

            copy = <classname>.__new__(*args,**kw)._setstate(<to_be_copied>._getstate())

        See python doc "pickling" (`__getstate__` and `__setstate__`) for details.
        """
        raise NotImplementedError, "To be able to use pickling you need to implement this method"

#===============================================================================
# Foundation framework for parameterized and param objects:
#===============================================================================

class Parentable(object):
    """
    Enable an Object to have a parent.
    
    Additionally this adds the parent_index, which is the index for the parent
    to look for in its parameter list.
    """
    _parent_ = None
    _parent_index_ = None
    def __init__(self, *args, **kwargs):
        super(Parentable, self).__init__()
    
    def has_parent(self):
        """
        Return whether this parentable object currently has a parent.
        """
        return self._parent_ is not None

    def _parent_changed(self):
        """
        Gets called, when the parent changed, so we can adjust our
        inner attributes according to the new parent.
        """
        raise NotImplementedError, "shouldnt happen, Parentable objects need to be able to change their parent"

    def _disconnect_parent(self, *args, **kw):
        """
        Disconnect this object from its parent
        """
        raise NotImplementedError, "Abstaract superclass"

    @property
    def _highest_parent_(self):
        """
        Gets the highest parent by traversing up to the root node of the hierarchy.
        """
        if self._parent_ is None:
            return self
        return self._parent_._highest_parent_

    def _notify_parent_change(self):
        """
        Dont do anything if in leaf node
        """
        pass

class Gradcheckable(Parentable):
    """
    Adds the functionality for an object to be gradcheckable.
    It is just a thin wrapper of a call to the highest parent for now.
    TODO: Can be done better, by only changing parameters of the current parameter handle,
    such that object hierarchy only has to change for those. 
    """
    def __init__(self, *a, **kw):
        super(Gradcheckable, self).__init__(*a, **kw)
    
    def checkgrad(self, verbose=0, step=1e-6, tolerance=1e-3):
        """
        Check the gradient of this parameter with respect to the highest parent's 
        objective function.
        This is a three point estimate of the gradient, wiggling at the parameters
        with a stepsize step.
        The check passes if either the ratio or the difference between numerical and 
        analytical gradient is smaller then tolerance.
        
        :param bool verbose: whether each parameter shall be checked individually.
        :param float step: the stepsize for the numerical three point gradient estimate.
        :param flaot tolerance: the tolerance for the gradient ratio or difference.
        """
        if self.has_parent():
            return self._highest_parent_._checkgrad(self, verbose=verbose, step=step, tolerance=tolerance)
        return self._checkgrad(self[''], verbose=verbose, step=step, tolerance=tolerance)
    def _checkgrad(self, param):
        """
        Perform the checkgrad on the model.
        TODO: this can be done more efficiently, when doing it inside here
        """
        raise NotImplementedError, "Need log likelihood to check gradient against"


class Nameable(Gradcheckable):
    """
    Make an object nameable inside the hierarchy.
    """
    def __init__(self, name, *a, **kw):
        super(Nameable, self).__init__(*a, **kw)
        self._name = name or self.__class__.__name__

    @property
    def name(self):
        """
        The name of this object
        """
        return self._name
    @name.setter
    def name(self, name):
        """
        Set the name of this object.
        Tell the parent if the name has changed.
        """
        from_name = self.name
        assert isinstance(name, str)
        self._name = name
        if self.has_parent():
            self._parent_._name_changed(self, from_name)
    def hierarchy_name(self, adjust_for_printing=True):
        """
        return the name for this object with the parents names attached by dots.
        
        :param bool adjust_for_printing: whether to call :func:`~adjust_for_printing()`
        on the names, recursively
        """
        if adjust_for_printing: adjust = lambda x: adjust_name_for_printing(x)
        else: adjust = lambda x: x
        if self.has_parent():
            return self._parent_.hierarchy_name() + "." + adjust(self.name)
        return adjust(self.name)

class Indexable(object):
    """
    Enable enraveled indexes and offsets for this object.
    The raveled index of an object is the index for its parameters in a flattened int array.
    """
    def __init__(self, *a, **kw):
        super(Indexable, self).__init__()
        
    def _raveled_index(self):
        """
        Flattened array of ints, specifying the index of this object.
        This has to account for shaped parameters!
        """
        raise NotImplementedError, "Need to be able to get the raveled Index"
        
    def _internal_offset(self):
        """
        The offset for this parameter inside its parent. 
        This has to account for shaped parameters!
        """
        return 0
    
    def _offset_for(self, param):
        """
        Return the offset of the param inside this parameterized object.
        This does not need to account for shaped parameters, as it
        basically just sums up the parameter sizes which come before param.
        """
        raise NotImplementedError, "shouldnt happen, offset required from non parameterization object?"
    
    def _raveled_index_for(self, param):
        """
        get the raveled index for a param
        that is an int array, containing the indexes for the flattened
        param inside this parameterized logic.
        """
        raise NotImplementedError, "shouldnt happen, raveld index transformation required from non parameterization object?"        
        

class Constrainable(Nameable, Indexable):
    """
    Make an object constrainable with Priors and Transformations.
    TODO: Mappings!!
    Adding a constraint to a Parameter means to tell the highest parent that
    the constraint was added and making sure that all parameters covered
    by this object are indeed conforming to the constraint.
    
    :func:`constrain()` and :func:`unconstrain()` are main methods here
    """
    def __init__(self, name, default_constraint=None, *a, **kw):
        super(Constrainable, self).__init__(name=name, default_constraint=default_constraint, *a, **kw)
        self._default_constraint_ = default_constraint
        from index_operations import ParameterIndexOperations
        self.constraints = ParameterIndexOperations()
        self.priors = ParameterIndexOperations()
        if self._default_constraint_ is not None:
            self.constrain(self._default_constraint_)
    
    def _disconnect_parent(self, constr=None, *args, **kw):
        """
        From Parentable:
        disconnect the parent and set the new constraints to constr
        """
        if constr is None:
            constr = self.constraints.copy()
        self.constraints.clear()
        self.constraints = constr
        self._parent_ = None
        self._parent_index_ = None
        self._connect_fixes()
        self._notify_parent_change()
        
    #===========================================================================
    # Fixing Parameters:
    #===========================================================================
    def constrain_fixed(self, value=None, warning=True, trigger_parent=True):
        """
        Constrain this parameter to be fixed to the current value it carries.

        :param warning: print a warning for overwriting constraints.
        """
        if value is not None:
            self[:] = value
        self.constrain(__fixed__, warning=warning, trigger_parent=trigger_parent)
        rav_i = self._highest_parent_._raveled_index_for(self)
        self._highest_parent_._set_fixed(rav_i)
    fix = constrain_fixed
    
    def unconstrain_fixed(self):
        """
        This parameter will no longer be fixed.
        """
        unconstrained = self.unconstrain(__fixed__)
        self._highest_parent_._set_unfixed(unconstrained)    
    unfix = unconstrain_fixed
    
    def _set_fixed(self, index):
        if not self._has_fixes(): self._fixes_ = np.ones(self.size, dtype=bool)
        self._fixes_[index] = FIXED
        if np.all(self._fixes_): self._fixes_ = None  # ==UNFIXED
    
    def _set_unfixed(self, index):
        if not self._has_fixes(): self._fixes_ = np.ones(self.size, dtype=bool)
        # rav_i = self._raveled_index_for(param)[index]
        self._fixes_[index] = UNFIXED
        if np.all(self._fixes_): self._fixes_ = None  # ==UNFIXED

    def _connect_fixes(self):
        fixed_indices = self.constraints[__fixed__]
        if fixed_indices.size > 0:
            self._fixes_ = np.ones(self.size, dtype=bool) * UNFIXED
            self._fixes_[fixed_indices] = FIXED
        else:
            self._fixes_ = None
    
    def _has_fixes(self):
        return hasattr(self, "_fixes_") and self._fixes_ is not None

    #===========================================================================
    # Prior Operations
    #===========================================================================
    def set_prior(self, prior, warning=True):
        """
        Set the prior for this object to prior.
        :param :class:`~GPy.priors.Prior` prior: a prior to set for this parameter
        :param bool warning: whether to warn if another prior was set for this parameter
        """
        repriorized = self.unset_priors()
        self._add_to_index_operations(self.priors, repriorized, prior, warning)
    
    def unset_priors(self, *priors):
        """
        Un-set all priors given from this parameter handle.
         
        """
        return self._remove_from_index_operations(self.priors, priors)
    
    def log_prior(self):
        """evaluate the prior"""
        if self.priors.size > 0:
            x = self._get_params()
            return reduce(lambda a, b: a + b, [p.lnpdf(x[ind]).sum() for p, ind in self.priors.iteritems()], 0)
        return 0.
    
    def _log_prior_gradients(self):
        """evaluate the gradients of the priors"""
        if self.priors.size > 0:
            x = self._get_params()
            ret = np.zeros(x.size)
            [np.put(ret, ind, p.lnpdf_grad(x[ind])) for p, ind in self.priors.iteritems()]
            return ret
        return 0.
        
    #===========================================================================
    # Constrain operations -> done
    #===========================================================================

    def constrain(self, transform, warning=True, trigger_parent=True):
        """
        :param transform: the :py:class:`GPy.core.transformations.Transformation`
                          to constrain the this parameter to.
        :param warning: print a warning if re-constraining parameters.

        Constrain the parameter to the given
        :py:class:`GPy.core.transformations.Transformation`.
        """
        if isinstance(transform, Transformation):
            self._param_array_[:] = transform.initialize(self._param_array_)
        reconstrained = self.unconstrain()
        self._add_to_index_operations(self.constraints, reconstrained, transform, warning)

    def unconstrain(self, *transforms):
        """
        :param transforms: The transformations to unconstrain from.

        remove all :py:class:`GPy.core.transformations.Transformation`
        transformats of this parameter object.
        """
        return self._remove_from_index_operations(self.constraints, transforms)
    
    def constrain_positive(self, warning=True, trigger_parent=True):
        """
        :param warning: print a warning if re-constraining parameters.

        Constrain this parameter to the default positive constraint.
        """
        self.constrain(Logexp(), warning=warning, trigger_parent=trigger_parent)

    def constrain_negative(self, warning=True, trigger_parent=True):
        """
        :param warning: print a warning if re-constraining parameters.

        Constrain this parameter to the default negative constraint.
        """
        self.constrain(NegativeLogexp(), warning=warning, trigger_parent=trigger_parent)

    def constrain_bounded(self, lower, upper, warning=True, trigger_parent=True):
        """
        :param lower, upper: the limits to bound this parameter to
        :param warning: print a warning if re-constraining parameters.

        Constrain this parameter to lie within the given range.
        """
        self.constrain(Logistic(lower, upper), warning=warning, trigger_parent=trigger_parent)

    def unconstrain_positive(self):
        """
        Remove positive constraint of this parameter.
        """
        self.unconstrain(Logexp())

    def unconstrain_negative(self):
        """
        Remove negative constraint of this parameter.
        """
        self.unconstrain(NegativeLogexp())

    def unconstrain_bounded(self, lower, upper):
        """
        :param lower, upper: the limits to unbound this parameter from

        Remove (lower, upper) bounded constrain from this parameter/
        """
        self.unconstrain(Logistic(lower, upper))
    
    def _parent_changed(self, parent):
        """
        From Parentable:
        Called when the parent changed
        """
        from index_operations import ParameterIndexOperationsView
        self.constraints = ParameterIndexOperationsView(parent.constraints, parent._offset_for(self), self.size)
        self.priors = ParameterIndexOperationsView(parent.priors, parent._offset_for(self), self.size)
        self._fixes_ = None
        for p in self._parameters_:
            p._parent_changed(parent)

    def _add_to_index_operations(self, which, reconstrained, what, warning):
        """
        Helper preventing copy code.
        This addes the given what (transformation, prior etc) to parameter index operations which.
        revonstrained are reconstrained indices.
        warn when reconstraining parameters if warning is True.
        TODO: find out which parameters have changed specifically
        """
        if warning and reconstrained.size > 0:
            # TODO: figure out which parameters have changed and only print those
            print "WARNING: reconstraining parameters {}".format(self.parameter_names() or self.name)
        which.add(what, self._raveled_index())

    def _remove_from_index_operations(self, which, what):
        """
        Helper preventing copy code.
        Remove given what (transform prior etc) from which param index ops. 
        """
        if len(what) == 0:
            transforms = which.properties()
        removed = np.empty((0,), dtype=int)
        for t in transforms:
            unconstrained = which.remove(t, self._raveled_index())
            removed = np.union1d(removed, unconstrained)
            if t is __fixed__:
                self._highest_parent_._set_unfixed(unconstrained)
        
        return removed

class OptimizationHandlable(Constrainable, Observable):
    """
    This enables optimization handles on an Object as done in GPy 0.4.

    `..._transformed`: make sure the transformations and constraints etc are handled
    """
    def __init__(self, name, default_constraint=None, *a, **kw):
        super(OptimizationHandlable, self).__init__(name, default_constraint=default_constraint, *a, **kw)
    
    def transform(self):
        [np.put(self._param_array_, ind, c.finv(self._param_array_[ind])) for c, ind in self.constraints.iteritems() if c != __fixed__]
    
    def untransform(self):
        [np.put(self._param_array_, ind, c.f(self._param_array_[ind])) for c, ind in self.constraints.iteritems() if c != __fixed__]
        
    def _get_params_transformed(self):
        # transformed parameters (apply transformation rules)
        p = self._param_array_.copy()
        [np.put(p, ind, c.finv(p[ind])) for c, ind in self.constraints.iteritems() if c != __fixed__]
        if self._has_fixes():
            return p[self._fixes_]
        return p

    def _set_params_transformed(self, p):
        if p is self._param_array_:
            p = p.copy()
        if self._has_fixes(): self._param_array_[self._fixes_] = p
        else: self._param_array_[:] = p
        self.untransform()
        self._trigger_params_changed()
        
    def _trigger_params_changed(self, trigger_parent=True):
        [p._trigger_params_changed(trigger_parent=False) for p in self._parameters_]
        if trigger_parent: min_priority = None
        else: min_priority = -np.inf
        self.notify_observers(None, min_priority)
    
    def _size_transformed(self):
        return self.size - self.constraints[__fixed__].size
#     
#     def _untransform_params(self, p):
#         # inverse apply transformations for parameters
#         #p = p.copy()
#         if self._has_fixes(): tmp = self._get_params(); tmp[self._fixes_] = p; p = tmp; del tmp
#         [np.put(p, ind, c.f(p[ind])) for c, ind in self.constraints.iteritems() if c != __fixed__]
#         return p
#     
#     def _get_params(self):
#         """
#         get all parameters
#         """
#         return self._param_array_
#         p = np.empty(self.size, dtype=np.float64)
#         if self.size == 0:
#             return p
#         [np.put(p, ind, par._get_params()) for ind, par in itertools.izip(self._param)]
#         return p
        
#     def _set_params(self, params, trigger_parent=True):
#         self._param_array_.flat = params
#         if trigger_parent: min_priority = None
#         else: min_priority = -np.inf
#         self.notify_observers(None, min_priority)
        # don't overwrite this anymore!
        #raise NotImplementedError, "Abstract superclass: This needs to be implemented in Param and Parameterizable"
    
    #===========================================================================
    # Optimization handles:
    #===========================================================================
    def _get_param_names(self):
        n = np.array([p.hierarchy_name() + '[' + str(i) + ']' for p in self.flattened_parameters for i in p._indices()])
        return n
    
    def _get_param_names_transformed(self):
        n = self._get_param_names()
        if self._has_fixes():
            return n[self._fixes_]
        return n

    #===========================================================================
    # Randomizeable
    #===========================================================================
    def randomize(self, rand_gen=np.random.normal, loc=0, scale=1, *args, **kwargs):
        """
        Randomize the model.
        Make this draw from the prior if one exists, else draw from given random generator
        
        :param rand_gen: numpy random number generator which takes args and kwargs
        :param flaot loc: loc parameter for random number generator
        :param float scale: scale parameter for random number generator
        :param args, kwargs: will be passed through to random number generator
        """
        # first take care of all parameters (from N(0,1))
        x = rand_gen(loc=loc, scale=scale, size=self._size_transformed(), *args, **kwargs)
        # now draw from prior where possible
        [np.put(x, ind, p.rvs(ind.size)) for p, ind in self.priors.iteritems() if not p is None]
        self._set_params_transformed(x) # makes sure all of the tied parameters get the same init (since there's only one prior object...)

    #===========================================================================
    # For shared memory arrays. This does nothing in Param, but sets the memory
    # for all parameterized objects
    #===========================================================================
    def _propagate_param_grad(self, parray, garray):
        pi_old_size = 0
        for pi in self._parameters_:
            pislice = slice(pi_old_size, pi_old_size+pi.size)

            self._param_array_[pislice] = pi._param_array_.ravel()#, requirements=['C', 'W']).flat
            self._gradient_array_[pislice] = pi._gradient_array_.ravel()#, requirements=['C', 'W']).flat
                
            pi._param_array_.data = parray[pislice].data
            pi._gradient_array_.data = garray[pislice].data
            
            pi._propagate_param_grad(parray[pislice], garray[pislice])
            pi_old_size += pi.size

class Parameterizable(OptimizationHandlable):
    def __init__(self, *args, **kwargs):
        super(Parameterizable, self).__init__(*args, **kwargs)
        from GPy.core.parameterization.lists_and_dicts import ArrayList
        _parameters_ = ArrayList()
        self.size = 0
        self._param_array_ = np.empty(self.size, dtype=np.float64)
        self._gradient_array_ = np.empty(self.size, dtype=np.float64)
        self._added_names_ = set()
    
    def parameter_names(self, add_self=False, adjust_for_printing=False, recursive=True):
        """
        Get the names of all parameters of this model. 
        
        :param bool add_self: whether to add the own name in front of names
        :param bool adjust_for_printing: whether to call `adjust_name_for_printing` on names
        :param bool recursive: whether to traverse through hierarchy and append leaf node names
        """
        if adjust_for_printing: adjust = lambda x: adjust_name_for_printing(x)
        else: adjust = lambda x: x
        if recursive: names = [xi for x in self._parameters_ for xi in x.parameter_names(add_self=True, adjust_for_printing=adjust_for_printing)]
        else: names = [adjust(x.name) for x in self._parameters_]
        if add_self: names = map(lambda x: adjust(self.name) + "." + x, names)
        return names
    
    @property
    def num_params(self):
        return len(self._parameters_)
    
    def _add_parameter_name(self, param, ignore_added_names=False):
        pname = adjust_name_for_printing(param.name)
        if ignore_added_names:
            self.__dict__[pname] = param
            return
        # and makes sure to not delete programmatically added parameters
        if pname in self.__dict__:
            if not (param is self.__dict__[pname]):
                if pname in self._added_names_:
                    del self.__dict__[pname]
                    self._add_parameter_name(param)
        elif pname not in dir(self):
            self.__dict__[pname] = param
            self._added_names_.add(pname)
            
    def _remove_parameter_name(self, param=None, pname=None):
        assert param is None or pname is None, "can only delete either param by name, or the name of a param"
        pname = adjust_name_for_printing(pname) or adjust_name_for_printing(param.name)
        if pname in self._added_names_:
            del self.__dict__[pname]
            self._added_names_.remove(pname)
        self._connect_parameters()

    def _name_changed(self, param, old_name):
        self._remove_parameter_name(None, old_name)
        self._add_parameter_name(param)
    
    #=========================================================================
    # Gradient handling
    #=========================================================================
    @property
    def gradient(self):
        return self._gradient_array_ 
    
    @gradient.setter
    def gradient(self, val):
        self._gradient_array_[:] = val
    #===========================================================================
    # def _collect_gradient(self, target):
    #     [p._collect_gradient(target[s]) for p, s in itertools.izip(self._parameters_, self._param_slices_)]
    #===========================================================================

    #===========================================================================
    # def _set_params(self, params, trigger_parent=True):
    #     [p._set_params(params[s], trigger_parent=False) for p, s in itertools.izip(self._parameters_, self._param_slices_)]
    #     if trigger_parent: min_priority = None
    #     else: min_priority = -np.inf
    #     self.notify_observers(None, min_priority)
    #===========================================================================

    #===========================================================================
    # def _set_gradient(self, g):
    #     [p._set_gradient(g[s]) for p, s in itertools.izip(self._parameters_, self._param_slices_)]
    #===========================================================================
        
    def add_parameter(self, param, index=None, _ignore_added_names=False):
        """
        :param parameters:  the parameters to add
        :type parameters:   list of or one :py:class:`GPy.core.param.Param`
        :param [index]:     index of where to put parameters
        
        :param bool _ignore_added_names: whether the name of the parameter overrides a possibly existing field

        Add all parameters to this param class, you can insert parameters
        at any given index using the :func:`list.insert` syntax
        """
        # if param.has_parent():
        #    raise AttributeError, "parameter {} already in another model, create new object (or copy) for adding".format(param._short())
        if param in self._parameters_ and index is not None:
            self.remove_parameter(param)
            self.add_parameter(param, index)
        elif param not in self._parameters_:
            if param.has_parent():
                parent = param._parent_
                while parent is not None:
                    if parent is self:
                        raise HierarchyError, "You cannot add a parameter twice into the hierarchy"
                    parent = parent._parent_
                param._parent_.remove_parameter(param)
            # make sure the size is set
            if index is None:
                self.constraints.update(param.constraints, self.size)
                self.priors.update(param.priors, self.size)
                self._parameters_.append(param)
            else:
                start = sum(p.size for p in self._parameters_[:index])
                self.constraints.shift_right(start, param.size)
                self.priors.shift_right(start, param.size)
                self.constraints.update(param.constraints, start)
                self.priors.update(param.priors, start)
                self._parameters_.insert(index, param)
            
            param.add_observer(self, self._pass_through_notify_observers, -np.inf)
            
            self.size += param.size

            self._connect_parameters(ignore_added_names=_ignore_added_names)
            self._notify_parent_change()
            self._connect_fixes()
        else:
            raise RuntimeError, """Parameter exists already added and no copy made"""


    def add_parameters(self, *parameters):
        """
        convenience method for adding several
        parameters without gradient specification
        """
        [self.add_parameter(p) for p in parameters]

    def remove_parameter(self, param):
        """
        :param param: param object to remove from being a parameter of this parameterized object.
        """
        if not param in self._parameters_:
            raise RuntimeError, "Parameter {} does not belong to this object, remove parameters directly from their respective parents".format(param._short())
        
        start = sum([p.size for p in self._parameters_[:param._parent_index_]])
        self._remove_parameter_name(param)
        self.size -= param.size
        del self._parameters_[param._parent_index_]
        
        param._disconnect_parent()
        param.remove_observer(self, self._pass_through_notify_observers)
        self.constraints.shift_left(start, param.size)
        
        self._connect_fixes()
        self._connect_parameters()
        self._notify_parent_change()
        
        parent = self._parent_
        while parent is not None:
            parent._connect_fixes()
            parent._connect_parameters()
            parent._notify_parent_change()
            parent = parent._parent_
        
    def _connect_parameters(self, ignore_added_names=False):
        # connect parameterlist to this parameterized object
        # This just sets up the right connection for the params objects
        # to be used as parameters
        # it also sets the constraints for each parameter to the constraints 
        # of their respective parents 
        if not hasattr(self, "_parameters_") or len(self._parameters_) < 1:
            # no parameters for this class
            return
        old_size = 0
        self._param_array_ = np.empty(self.size, dtype=np.float64)
        self._gradient_array_ = np.empty(self.size, dtype=np.float64)
        
        self._param_slices_ = []
        
        for i, p in enumerate(self._parameters_):
            p._parent_ = self
            p._parent_index_ = i
            
            pslice = slice(old_size, old_size+p.size)
            
            # first connect all children
            p._propagate_param_grad(self._param_array_[pslice], self._gradient_array_[pslice])            
            
            # then connect children to self
            self._param_array_[pslice] = p._param_array_.ravel()#, requirements=['C', 'W']).ravel(order='C')
            self._gradient_array_[pslice] = p._gradient_array_.ravel()#, requirements=['C', 'W']).ravel(order='C')
            
            if not p._param_array_.flags['C_CONTIGUOUS']:
                import ipdb;ipdb.set_trace()
            p._param_array_.data = self._param_array_[pslice].data
            p._gradient_array_.data = self._gradient_array_[pslice].data
            
            self._param_slices_.append(pslice)
            
            self._add_parameter_name(p, ignore_added_names=ignore_added_names)
            old_size += p.size
            
    #===========================================================================
    # notification system
    #===========================================================================
    def _parameters_changed_notification(self, which):
        self.parameters_changed()
    def _pass_through_notify_observers(self, which):
        self.notify_observers(which)
    
    #===========================================================================
    # TODO: not working yet
    #===========================================================================
    def copy(self):
        """Returns a (deep) copy of the current model"""
        import copy
        from .index_operations import ParameterIndexOperations, ParameterIndexOperationsView
        from .lists_and_dicts import ArrayList

        dc = dict()
        for k, v in self.__dict__.iteritems():
            if k not in ['_parent_', '_parameters_', '_parent_index_', '_observer_callables_'] + self.parameter_names(recursive=False):
                if isinstance(v, (Constrainable, ParameterIndexOperations, ParameterIndexOperationsView)):
                    dc[k] = v.copy()
                else:
                    dc[k] = copy.deepcopy(v)
            if k == '_parameters_':
                params = [p.copy() for p in v]
            
        dc['_parent_'] = None
        dc['_parent_index_'] = None
        dc['_observer_callables_'] = []
        dc['_parameters_'] = ArrayList()
        dc['constraints'].clear()
        dc['priors'].clear()
        dc['size'] = 0

        s = self.__new__(self.__class__)
        s.__dict__ = dc
        
        for p in params:
            s.add_parameter(p, _ignore_added_names=True)
        
        return s
    
    #===========================================================================
    # From being parentable, we have to define the parent_change notification
    #===========================================================================
    def _notify_parent_change(self):
        """
        Notify all parameters that the parent has changed
        """
        for p in self._parameters_:
            p._parent_changed(self)

    def parameters_changed(self):
        """
        This method gets called when parameters have changed.
        Another way of listening to param changes is to
        add self as a listener to the param, such that
        updates get passed through. See :py:function:``GPy.core.param.Observable.add_observer``
        """
        pass

