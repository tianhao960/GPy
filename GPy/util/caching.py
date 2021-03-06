from ..core.parameterization.parameter_core import Observable
import itertools

class Cacher(object):
    """




    """

    def __init__(self, operation, limit=5, ignore_args=()):
        self.limit = int(limit)
        self.ignore_args = ignore_args
        self.operation=operation
        self.cached_inputs = []
        self.cached_outputs = []
        self.inputs_changed = []

    def __call__(self, *args):
        """
        A wrapper function for self.operation,
        """

        #ensure that specified arguments are ignored
        if len(self.ignore_args) != 0:
            oa = [a for i,a in enumerate(args) if i not in self.ignore_args]
        else:
            oa = args

        # this makes sure we only add an observer once, and that None can be in args
        observable_args = []
        for a in oa:
            if (not any(a is ai for ai in observable_args)) and a is not None:
                observable_args.append(a)

        #make sure that all the found argument really are observable:
        #otherswise don't cache anything, pass args straight though
        if not all([isinstance(arg, Observable) for arg in observable_args]):
            return self.operation(*args)

        # TODO: WARNING !!! Cache OFFSWITCH !!! WARNING
        # return self.operation(*args)

        #if the result is cached, return the cached computation
        state = [all(a is b for a, b in itertools.izip_longest(args, cached_i)) for cached_i in self.cached_inputs]
        if any(state):
            i = state.index(True)
            if self.inputs_changed[i]:
                #(elements of) the args have changed since we last computed: update
                self.cached_outputs[i] = self.operation(*args)
                self.inputs_changed[i] = False
            return self.cached_outputs[i]
        else:
            #first time we've seen these arguments: compute

            #first make sure the depth limit isn't exceeded
            if len(self.cached_inputs) == self.limit:
                args_ = self.cached_inputs.pop(0)
                [a.remove_observer(self, self.on_cache_changed) for a in args_ if a is not None]
                self.inputs_changed.pop(0)
                self.cached_outputs.pop(0)

            #compute
            self.cached_inputs.append(args)
            self.cached_outputs.append(self.operation(*args))
            self.inputs_changed.append(False)
            [a.add_observer(self, self.on_cache_changed) for a in observable_args]
            return self.cached_outputs[-1]#Max says return.

    def on_cache_changed(self, arg):
        """
        A callback funtion, which sets local flags when the elements of some cached inputs change

        this function gets 'hooked up' to the inputs when we cache them, and upon their elements being changed we update here.
        """
        self.inputs_changed = [any([a is arg for a in args]) or old_ic for args, old_ic in zip(self.cached_inputs, self.inputs_changed)]

    def reset(self, obj):
        """
        Totally reset the cache
        """
        [[a.remove_observer(self, self.on_cache_changed) for a in args if isinstance(a, Observable)] for args in self.cached_inputs]
        [[a.remove_observer(self, self.reset) for a in args if isinstance(a, Observable)] for args in self.cached_inputs]
        self.cached_inputs = []
        self.cached_outputs = []
        self.inputs_changed = []

class Cache_this(object):
    """
    A decorator which can be applied to bound methods in order to cache them
    """
    def __init__(self, limit=5, ignore_args=()):
        self.limit = limit
        self.ignore_args = ignore_args
        self.c = None
    def __call__(self, f):
        def f_wrap(*args):
            if self.c is None:
                self.c = Cacher(f, self.limit, ignore_args=self.ignore_args)
            return self.c(*args)
        f_wrap._cacher = self
        f_wrap.__doc__ = "**cached**\n\n" + (f.__doc__ or "")
        return f_wrap
