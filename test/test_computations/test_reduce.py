import time
import itertools

import numpy
import pytest

from helpers import *
from reikna.reduce import Reduce, Predicate, predicate_sum
from reikna.helpers import template_def
from reikna.cluda import Snippet
import reikna.cluda.dtypes as dtypes


shapes = [
    (2,), (13,), (1535,), (512 * 231,),
    (140, 3), (13, 598), (1536, 789),
    (5, 15, 19), (134, 25, 23), (145, 56, 178)]
shapes_and_axes = [(shape, axis) for shape, axis in itertools.product(shapes, [None, 0, 1, 2])
    if axis is None or axis < len(shape)]
shapes_and_axes_ids = [str(shape) + "," + str(axis) for shape, axis in shapes_and_axes]


@pytest.mark.parametrize(('shape', 'axis'), shapes_and_axes, ids=shapes_and_axes_ids)
def test_normal(thr, shape, axis):

    a = get_test_array(shape, numpy.int64)
    a_dev = thr.to_device(a)

    rd = Reduce(a, predicate_sum(numpy.int64), axes=(axis,) if axis is not None else None)

    b_dev = thr.empty_like(rd.parameter.output)

    b_ref = a.sum(axis)
    if len(b_ref.shape) == 0:
        b_ref = numpy.array([b_ref], numpy.int64)

    rdc = rd.compile(thr)
    rdc(b_dev, a_dev)

    assert diff_is_negligible(b_dev.get(), b_ref)


def test_nondefault_function(thr):

    shape = (100, 100)
    a = get_test_array(shape, numpy.int64)
    a_dev = thr.to_device(a)
    b_ref = a.sum(0)

    predicate = Predicate(
        Snippet.create(lambda v1, v2: "return ${v1} + ${v2};"),
        0)

    rd = Reduce(a_dev, predicate, axes=(0,))

    b_dev = thr.empty_like(rd.parameter.output)

    rdc = rd.compile(thr)
    rdc(b_dev, a_dev)

    assert diff_is_negligible(b_dev.get(), b_ref)


def test_nonsequential_axes(thr):

    shape = (50, 40, 30, 20)
    a = get_test_array(shape, numpy.int64)
    a_dev = thr.to_device(a)
    b_ref = a.sum(0).sum(1) # sum over axes 0 and 2 of the initial array

    rd = Reduce(a_dev, predicate_sum(numpy.int64), axes=(0,2))

    b_dev = thr.empty_like(rd.parameter.output)

    rdc = rd.compile(thr)
    rdc(b_dev, a_dev)

    assert diff_is_negligible(b_dev.get(), b_ref)


def test_structure_type(thr):

    shape = (100, 100)
    dtype = numpy.dtype([
        ('i1', numpy.int32),
        ('nested', numpy.dtype([
            ('c', numpy.complex64)])),
        ('i2', numpy.int32)])

    a = get_test_array(shape, dtype)
    a_dev = thr.to_device(a)

    # Have to construct the resulting array manually,
    # since numpy cannot reduce arrays with struct dtypes.
    b_ref = numpy.empty(100, dtype)
    b_ref['i1'] = a['i1'].sum(0)
    b_ref['nested']['c'] = a['nested']['c'].sum(0)
    b_ref['i2'] = a['i2'].sum(0)

    predicate = Predicate(
        Snippet.create(lambda v1, v2: """
            ${ctype} result;
            result.i1 = ${v1}.i1 + ${v2}.i1;
            result.nested.c = ${v1}.nested.c + ${v2}.nested.c;
            result.i2 = ${v1}.i2 + ${v2}.i2;
            return result;
            """,
            render_kwds=dict(
                ctype=dtypes.ctype_module(dtype))),
        numpy.zeros(1, dtype)[0])

    rd = Reduce(a_dev, predicate, axes=(0,))

    b_dev = thr.empty_like(rd.parameter.output)

    rdc = rd.compile(thr)
    rdc(b_dev, a_dev)

    assert diff_is_negligible(b_dev.get(), b_ref)

@pytest.mark.perf
@pytest.mark.returns('GFLOPS')
def test_summation(thr):

    perf_size = 2 ** 20
    dtype = numpy.int64

    a = get_test_array(perf_size, dtype)
    a_dev = thr.to_device(a)

    rd = Reduce(a, predicate_sum(dtype))

    b_dev = thr.empty_like(rd.parameter.output)
    b_ref = numpy.array([a.sum()], dtype)

    rdc = rd.compile(thr)

    attempts = 10
    t1 = time.time()
    for i in range(attempts):
        rdc(b_dev, a_dev)
    thr.synchronize()
    t2 = time.time()

    #print rdc._kernel_calls[-1]._kernel._program.source
    assert diff_is_negligible(b_dev.get(), b_ref)

    return (t2 - t1) / attempts, perf_size

