"""Chay mot tap (episode) va tra ve tong thuong + thong ke."""
from sim.env import CarEnv, EnvConfig


def make_env(stage=3, max_steps=900, record=False, **kw):
    cfg = EnvConfig(stage=stage, max_steps=max_steps, record=record, **kw)
    return CarEnv(cfg)


def rollout(policy, env, seed, render_cb=None):
    obs = env.reset(seed)
    if hasattr(policy, "reset"):
        policy.reset()
    total = 0.0
    done = False
    info = {}
    while not done:
        a = policy.act(obs)
        obs, rew, done, info = env.step(a)
        total += rew
        if render_cb is not None:
            render_cb(env)
    stats = {
        "return": total,
        "steps": env.steps,
        "arrivals": env.arrivals,
        "charged": env.charged,
        "distance": env.distance,
        "bumps": env.bumps,
        "fell": bool(info.get("fell", False)),
        "flat": bool(info.get("flat", False)),
        "battery": env.robot.battery,
        "cells": len(env.visited),
    }
    return total, stats
