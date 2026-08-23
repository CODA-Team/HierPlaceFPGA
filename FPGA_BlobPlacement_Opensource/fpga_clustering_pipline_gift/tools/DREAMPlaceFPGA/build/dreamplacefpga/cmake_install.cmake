# Install script for directory: /work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/DREAMPlaceFPGA")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "RELEASE")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "1")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "FALSE")
endif()

# Set default install directory permissions.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/usr/bin/objdump")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/cmake_install.cmake")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/dreamplacefpga" TYPE FILE FILES
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/BasicPlace.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/BasicPlace01071003.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/BasicPlace_01072050.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/EvalMetrics.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/IFWriter.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/NesterovAcceleratedGradientOptimizer.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/NonLinearPlace.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/NonLinearPlace01071003.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/Params.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/Params01071003.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/Params_old.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/PlaceDB.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/PlaceDB01071003.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/PlaceObj.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/PlaceObj01071003.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/Placer.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/Placer_01071003.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/Placer_debug.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/Placer_old.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/Timer.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/__init__.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/configure.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/extract_movable.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/paramsFPGA.json"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/plot_placement_metrics.py"
    "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/via_pl.py"
    )
endif()

