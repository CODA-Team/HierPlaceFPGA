# Validation Summary

Validated in Docker container `638feef5705b` on 2026-05-15.

Commands run from package root:

```bash
scripts/check_environment_new_server.sh
scripts/run_smoke_case1_iter20.sh /tmp/fpga_pkg_smoke_case1_iter20
```

Results:

- Python syntax/import checks passed.
- PyTorch detected as `1.7.1`, CUDA build `11.0`, `torch._C._GLIBCXX_USE_CXX11_ABI=False`.
- DREAMPlaceFPGA native op imports passed.
- hMETIS tiny graph smoke passed.
- Julia `K_SpecPartWrapper.jl` tiny graph smoke passed.
- `public_release/case_1` conversion passed.
- Full short smoke flow generated `/tmp/fpga_pkg_smoke_case1_iter20/4_final_input`.
- Final DREAMPlaceFPGA compatibility run also completed with `iter20`; overflow was not expected to converge at this tiny iteration budget.

The package itself does not include the `/tmp/fpga_pkg_smoke_case1_iter20` validation output.
