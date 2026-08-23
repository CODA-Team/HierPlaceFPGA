# Install script for directory: /work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/ops

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
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/utility/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/dct/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/pin_pos/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/density_map/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/density_potential/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/logsumexp_wirelength/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/draw_place/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/electric_potential/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/hpwl/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/move_boundary/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/weighted_average_wirelength/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/timing_net_wirelength/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/place_io/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/precondWL/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/precondTiming/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/sortNode2Pin/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/demandMap/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/dsp_ram_legalization/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/lut_ff_legalization/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/pin_utilization/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/rudy/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/adjust_node_area/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/clustering_compatibility/cmake_install.cmake")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/dreamplacefpga/ops/timing/cmake_install.cmake")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/dreamplacefpga/ops" TYPE FILE FILES "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/dreamplacefpga/ops/__init__.py")
endif()

