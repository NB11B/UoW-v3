# Protocol Specification: Transition Relation & Guards

## 1. Route Evaluation

Each contract \(\Gamma\) contains an ordered sequence of routes \(R_0, R_1, \dots, R_{k-1}\).
Route evaluation is deterministic:
1. Routes are evaluated strictly in ascending index order.
2. The first route whose guards all evaluate to `true` is selected.
3. If no route matches, the transition aborts with `NO_MATCHING_ROUTE`.

## 2. Guard Operations

| Operator | Symbol | Semantic Evaluation |
|---|---|---|
| `EQ` | `==` | \(V(\text{key}) = \text{value}\) |
| `NEQ` | `!=` | \(V(\text{key}) \ne \text{value}\) |
| `LT` | `<` | \(V(\text{key}) < \text{value}\) |
| `LTE` | `<=` | \(V(\text{key}) \le \text{value}\) |
| `GT` | `>` | \(V(\text{key}) > \text{value}\) |
| `GTE` | `>=` | \(V(\text{key}) \ge \text{value}\) |
| `IN` | \(\in\) | \(V(\text{key}) \in \text{value}\) |
| `NOT_IN` | \(\notin\) | \(V(\text{key}) \notin \text{value}\) |
| `CONTAINS` | \(\ni\) | \(\text{value} \in V(\text{key})\) |
| `PREFIX` | \(\text{sw}\) | \(V(\text{key})\) starts with string value |
| `SUFFIX` | \(\text{ew}\) | \(V(\text{key})\) ends with string value |

## 3. Mutation Operations

| Operator | Semantic Action |
|---|---|
| `SET` | Set \(V(\text{key}) \leftarrow \text{value}\) |
| `INCREMENT` | Set \(V(\text{key}) \leftarrow V(\text{key}) + \text{value}\) |
| `DECREMENT` | Set \(V(\text{key}) \leftarrow V(\text{key}) - \text{value}\) |
| `DELETE` | Remove key from state values |
| `APPEND` | Append item to list value |
| `EXTEND` | Extend list with iterable value |
