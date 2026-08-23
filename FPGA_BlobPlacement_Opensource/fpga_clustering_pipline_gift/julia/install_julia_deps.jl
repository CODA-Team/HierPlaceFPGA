using Pkg

root = normpath(joinpath(@__DIR__, ".."))
graph_laplacians = joinpath(root, "external", "HypergraphPartitioning-main", "K_SpecPart", "GraphLaplacians")

Pkg.add([
    "ArgParse",
    "JSON",
    "Graphs",
    "LightGraphs",
    "SimpleWeightedGraphs",
    "SimpleGraphs",
    "SimpleTraits",
    "DataStructures",
    "Combinatorics",
    "Laplacians",
    "LinearMaps",
    "IterativeSolvers",
    "LDLFactorizations",
    "MultivariateStats",
    "Metis",
    "Shuffle",
    "JuMP",
    "Gurobi",
])

if isdir(graph_laplacians)
    Pkg.develop(PackageSpec(path=graph_laplacians))
end

# Rebuild Gurobi.jl after GUROBI_HOME / GRB_LICENSE_FILE is set.
try
    Pkg.build("Gurobi")
catch e
    @warn "Pkg.build(\"Gurobi\") failed; set GUROBI_HOME and license first, then rerun." exception=(e, catch_backtrace())
end

Pkg.precompile()
println("Julia dependency installation finished")
