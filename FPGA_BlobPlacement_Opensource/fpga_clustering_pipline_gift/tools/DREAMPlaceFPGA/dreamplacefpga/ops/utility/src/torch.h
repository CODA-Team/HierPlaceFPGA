/**
 * @file   torch.h
 * @author Yibo Lin (DREAMPlace)
 * @date   Mar 2019
 * @brief  Required headers from torch - FIXED FOR PYTORCH 1.7
 */
#ifndef _DREAMPLACE_UTILITY_TORCH_H
#define _DREAMPLACE_UTILITY_TORCH_H

#include <torch/extension.h>
#include <limits>

// PyTorch 1.7 兼容性定义
#if TORCH_VERSION_MAJOR >= 1 && TORCH_VERSION_MINOR >= 7
#define DREAMPLACE_TENSOR_DATA_PTR(TENSOR, TYPE) \
  ((TENSOR.defined())? TENSOR.data_ptr<TYPE>() : nullptr)
#define DREAMPLACE_TENSOR_SCALARTYPE(TENSOR) TENSOR.scalar_type()
#else
#define DREAMPLACE_TENSOR_DATA_PTR(TENSOR, TYPE) \
  ((TENSOR.defined())? TENSOR.data<TYPE>() : nullptr)
#define DREAMPLACE_TENSOR_SCALARTYPE(TENSOR) TENSOR.type().scalarType()
#endif

// 为 PyTorch 1.7 重新定义 AT_PRIVATE_CASE_TYPE
#define AT_PRIVATE_CASE_TYPE(NAME, enum_type, type, ...) \
  case enum_type: {                                      \
    using scalar_t = type;                               \
    return __VA_ARGS__();                                \
  }

#define DREAMPLACE_PRIVATE_CASE_TYPE(NAME, enum_type, type, ...) \
  AT_PRIVATE_CASE_TYPE(NAME, enum_type, type, __VA_ARGS__)

// 命名空间定义
#define DREAMPLACE_BEGIN_NAMESPACE namespace DreamPlaceFPGA {
#define DREAMPLACE_END_NAMESPACE }
#define DREAMPLACE_NAMESPACE DreamPlaceFPGA
#define DREAMPLACE_STD_NAMESPACE std

// 检查宏 - 统一定义
#define CHECK_CPU(x) AT_ASSERTM(!x.is_cuda(), #x " must be a tensor on CPU")
#define CHECK_CUDA(x) AT_ASSERTM(x.is_cuda(), #x " must be a tensor on CUDA")
#define CHECK_FLAT(x) AT_ASSERTM(x.ndimension() == 1, #x " must be a flat tensor")
#define CHECK_EVEN(x) AT_ASSERTM((x.numel() & 1) == 0, #x " must have even number of elements")
#define CHECK_CONTIGUOUS(x) AT_ASSERTM(x.is_contiguous(), #x " must be contiguous")

// 调度宏
#define DREAMPLACE_DISPATCH_FLOATING_TYPES(TENSOR, NAME, ...)                         \
  [&] {                                                                               \
    at::ScalarType _st = DREAMPLACE_TENSOR_SCALARTYPE(TENSOR);                        \
    switch (_st) {                                                                    \
      DREAMPLACE_PRIVATE_CASE_TYPE(NAME, at::ScalarType::Double, double, __VA_ARGS__) \
      DREAMPLACE_PRIVATE_CASE_TYPE(NAME, at::ScalarType::Float, float, __VA_ARGS__)   \
      default:                                                                        \
        AT_ERROR(#NAME, " not implemented for '", toString(_st), "'");                \
    }                                                                                 \
  }()

// FFT API 兼容性 - 专门为 PyTorch 1.7.1 修正
#if TORCH_VERSION_MAJOR >= 1 && TORCH_VERSION_MINOR >= 8
// PyTorch 1.8+ 使用新的 FFT API
#include <ATen/ops/fft.h>
#else
// PyTorch 1.7.1 及以下使用旧的 FFT API
#include <ATen/ATen.h>

// 为 PyTorch 1.7.1 添加 FFT 兼容函数
namespace at {
namespace ops {
// 兼容 rfft 函数
inline at::Tensor rfft(const at::Tensor& self, int64_t n, bool normalized = false, bool onesided = true) {
    return at::rfft(self, n, normalized, onesided);
}
// 兼容 irfft 函数
inline at::Tensor irfft(const at::Tensor& self, int64_t n, bool normalized = false, bool onesided = true, int64_t signal_ndim = 1) {
    return at::irfft(self, signal_ndim, normalized, onesided, at::IntArrayRef({n}));
}
} // namespace ops
} // namespace at
#endif

// 移除原始文件中可能导致问题的复杂条件逻辑
// 为 DREAMPlaceFPGA 明确针对 PyTorch 1.7 定制

#endif // _DREAMPLACE_UTILITY_TORCH_H