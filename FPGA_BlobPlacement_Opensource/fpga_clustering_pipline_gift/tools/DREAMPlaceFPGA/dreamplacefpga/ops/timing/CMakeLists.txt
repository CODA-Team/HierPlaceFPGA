# timing/CMakeLists.txt
include_directories(/opt/conda/include/python3.8)
include_directories(/opt/conda/include)
include_directories(/opt/conda/lib/python3.8/site-packages/torch/include)

set(OP_NAME timing)

set(TARGET_NAME ${OP_NAME})

# 设置包含目录
set(INCLUDE_DIRS 
  ${CMAKE_CURRENT_SOURCE_DIR}/..
  ${EIGEN3_INCLUDE_DIR}
  ${TORCH_INSTALL_PREFIX}/include
  ${TORCH_INSTALL_PREFIX}/include/torch/csrc/api/include
  ${CUDA_INCLUDE_DIRS}
  )

# 设置链接库
set(LINK_LIBS 
  utility_cxx
  OpenMP::OpenMP_CXX
  ${TORCH_LIBRARIES}
  ${ZLIB_LIBRARIES}
  )

# 添加 CPU 版本的 timer_cpp 模块
add_pytorch_extension(timer_cpp 
  src/timer.cpp
  EXTRA_INCLUDE_DIRS ${INCLUDE_DIRS}
  EXTRA_LINK_LIBRARIES ${LINK_LIBS}
  EXTRA_DEFINITIONS ENABLE_CUDA=0
  )

# 如果启用 CUDA，添加 CUDA 版本
if(CUDA_FOUND)
  # 创建 CUDA 静态库
  cuda_add_library(timer_cuda_tmp STATIC
    src/timer_cuda.cpp
    src/timer_cuda_kernel.cu
  )
  target_include_directories(timer_cuda_tmp PRIVATE ${INCLUDE_DIRS})
  
  # 添加 CUDA 版本的 timer_cuda 模块
  add_pytorch_extension(timer_cuda 
    src/timer_cuda.cpp
    EXTRA_INCLUDE_DIRS ${INCLUDE_DIRS}
    EXTRA_LINK_LIBRARIES ${LINK_LIBS} timer_cuda_tmp
    EXTRA_DEFINITIONS ENABLE_CUDA=1
    )
endif()

# 安装目标
install(TARGETS 
  timer_cpp
  DESTINATION dreamplacefpga/ops/${OP_NAME})

if(CUDA_FOUND)
  install(TARGETS 
    timer_cuda
    DESTINATION dreamplacefpga/ops/${OP_NAME})
endif()

# 安装 Python 源文件
file(GLOB INSTALL_SRCS ${CMAKE_CURRENT_SOURCE_DIR}/*.py)
install(FILES ${INSTALL_SRCS} DESTINATION dreamplacefpga/ops/${OP_NAME})