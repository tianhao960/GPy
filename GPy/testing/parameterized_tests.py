'''
Created on Feb 13, 2014

@author: maxzwiessele
'''
import unittest
import GPy
import numpy as np
from GPy.core.parameterization.parameter_core import HierarchyError

class Test(unittest.TestCase):

    def setUp(self):
        self.rbf = GPy.kern.RBF(1)
        self.white = GPy.kern.White(1)
        from GPy.core.parameterization import Param
        from GPy.core.parameterization.transformations import Logistic
        self.param = Param('param', np.random.rand(25,2), Logistic(0, 1))
        
        self.test1 = GPy.core.Parameterized("test model")
        self.test1.add_parameter(self.white)
        self.test1.add_parameter(self.rbf, 0)
        self.test1.add_parameter(self.param)
        
        x = np.linspace(-2,6,4)[:,None]
        y = np.sin(x)
        self.testmodel = GPy.models.GPRegression(x,y)
        
    def test_add_parameter(self):
        self.assertEquals(self.rbf._parent_index_, 0)
        self.assertEquals(self.white._parent_index_, 1)
        pass
    
    def test_fixes(self):
        self.white.fix(warning=False)
        self.test1.remove_parameter(self.test1.param)
        self.assertTrue(self.test1._has_fixes())

        from GPy.core.parameterization.transformations import FIXED, UNFIXED
        self.assertListEqual(self.test1._fixes_.tolist(),[UNFIXED,UNFIXED,FIXED])

        self.test1.add_parameter(self.white, 0)
        self.assertListEqual(self.test1._fixes_.tolist(),[FIXED,UNFIXED,UNFIXED])
        
    def test_remove_parameter(self):
        from GPy.core.parameterization.transformations import FIXED, UNFIXED, __fixed__, Logexp
        self.white.fix()
        self.test1.remove_parameter(self.white)
        self.assertIs(self.test1._fixes_,None)
        
        self.assertListEqual(self.white._fixes_.tolist(), [FIXED])
        self.assertEquals(self.white.constraints._offset, 0)
        self.assertIs(self.test1.constraints, self.rbf.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.param.constraints._param_index_ops)        
        
        self.test1.add_parameter(self.white, 0)
        self.assertIs(self.test1.constraints, self.white.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.rbf.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.param.constraints._param_index_ops)        
        self.assertListEqual(self.test1.constraints[__fixed__].tolist(), [0])
        self.assertIs(self.white._fixes_,None)
        self.assertListEqual(self.test1._fixes_.tolist(),[FIXED] + [UNFIXED] * 52)
        
        self.test1.remove_parameter(self.white)
        self.assertIs(self.test1._fixes_,None)
        self.assertListEqual(self.white._fixes_.tolist(), [FIXED])
        self.assertIs(self.test1.constraints, self.rbf.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.param.constraints._param_index_ops)
        self.assertListEqual(self.test1.constraints[Logexp()].tolist(), [0,1])
        
    def test_add_parameter_already_in_hirarchy(self):
        self.assertRaises(HierarchyError, self.test1.add_parameter, self.white._parameters_[0])        
        
    def test_default_constraints(self):
        self.assertIs(self.rbf.variance.constraints._param_index_ops, self.rbf.constraints._param_index_ops)
        self.assertIs(self.test1.constraints, self.rbf.constraints._param_index_ops)
        self.assertListEqual(self.rbf.constraints.indices()[0].tolist(), range(2))
        from GPy.core.parameterization.transformations import Logexp
        kern = self.rbf+self.white
        self.assertListEqual(kern.constraints[Logexp()].tolist(), range(3))

    def test_constraints(self):
        self.rbf.constrain(GPy.transformations.Square(), False)
        self.assertListEqual(self.test1.constraints[GPy.transformations.Square()].tolist(), range(2))
        self.assertListEqual(self.test1.constraints[GPy.transformations.Logexp()].tolist(), [2])
        
        self.test1.remove_parameter(self.rbf)
        self.assertListEqual(self.test1.constraints[GPy.transformations.Square()].tolist(), [])

    def test_constraints_views(self):
        self.assertEqual(self.white.constraints._offset, 2)
        self.assertEqual(self.rbf.constraints._offset, 0)
        self.assertEqual(self.param.constraints._offset, 3)

    def test_fixing_randomize(self):
        self.white.fix(warning=False)
        val = float(self.test1.white.variance)
        self.test1.randomize()
        self.assertEqual(val, self.white.variance)

    def test_fixing_optimize(self):
        self.testmodel.kern.lengthscale.fix()
        val = float(self.testmodel.kern.lengthscale)
        self.testmodel.randomize()
        self.assertEqual(val, self.testmodel.kern.lengthscale)

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.test_add_parameter']
    unittest.main()