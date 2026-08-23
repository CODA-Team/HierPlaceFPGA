module GraphLaplacians

using SparseArrays
using LinearAlgebra

"""
    degree_matrix(adj::SparseMatrixCSC)

Return a sparse diagonal matrix where each diagonal entry is the degree
(row sum) of the corresponding node in the adjacency matrix `adj`.
"""
function degree_matrix(adj::SparseMatrixCSC)
    d = vec(sum(adj, dims=2))
    return spdiagm(0 => d)
end

"""
    degrees(adj::SparseMatrixCSC)

Return a vector of node degrees from adjacency matrix `adj`.
"""
function degrees(adj::SparseMatrixCSC)
    return vec(sum(adj, dims=2))
end

export degree_matrix, degrees

end # module
