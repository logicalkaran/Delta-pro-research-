"""Compact NumPy probabilistic direction model with regularization and calibration."""
from __future__ import annotations
import numpy as np

FEATURES=['imb5','imb10','delta5','delta30','delta60','ret5','ret30','ret60','cvd_slope30','spread_bps','ofi_proxy','pressure_capacity','liquidity_state','liquidity_fragility','flow_acceleration','momentum_composite','flow_price_divergence','depth_asymmetry','toxicity_score']

class ProbabilisticModel:
    def __init__(self,l2=1.0,lr=.05,epochs=500): self.l2=l2; self.lr=lr; self.epochs=epochs; self.mean=None; self.std=None; self.w=None; self.bias=0.; self.cal_a=1.; self.cal_b=0.
    def matrix(self,rows):
        return np.asarray([[float(r.get(f,0) or 0) for f in FEATURES] for r in rows],dtype=float)
    @staticmethod
    def _sigmoid(z): return 1/(1+np.exp(-np.clip(z,-30,30)))
    def fit(self,rows,y):
        X=self.matrix(rows); y=np.asarray(y,dtype=float)
        if len(X)==0: raise ValueError('empty training set')
        self.mean=X.mean(0); self.std=X.std(0); self.std[self.std<1e-9]=1
        Z=(X-self.mean)/self.std; self.w=np.zeros(Z.shape[1]); self.bias=0.
        for _ in range(self.epochs):
            p=self._sigmoid(Z@self.w+self.bias); g=(Z.T@(p-y))/len(y)+self.l2*self.w; gb=float(np.mean(p-y))
            self.w-=self.lr*g; self.bias-=self.lr*gb
        return self
    def predict_proba(self,rows):
        X=(self.matrix(rows)-self.mean)/self.std; p=self._sigmoid(X@self.w+self.bias)
        return p
    def calibrate(self,rows,y):
        p=np.clip(self.predict_proba(rows),1e-6,1-1e-6); z=np.log(p/(1-p)); y=np.asarray(y,float)
        A=np.column_stack([z,np.ones(len(z))]); theta=np.linalg.solve(A.T@A+1e-6*np.eye(2),A.T@np.log(np.clip(y,.01,.99)/(1-np.clip(y,.01,.99))))
        self.cal_a=float(theta[0]); self.cal_b=float(theta[1]); return self
    def predict_calibrated(self,rows):
        p=np.clip(self.predict_proba(rows),1e-6,1-1e-6); z=np.log(p/(1-p)); return self._sigmoid(self.cal_a*z+self.cal_b)
