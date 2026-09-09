function add(a, b) {
  return a + b;
}
function mul(a, b) {
  return a * b;
}
function max(a, b) {
  if (a > b) {
    return a;
  } else {
    return b;
  }
  return 0;
}
function main() {
  print(add(2, 3));
  print(add(2 * 3, 4 + 1));
  let m: i32 = max(max(1, 5), max(3, 4));
  print(m);
  print(max(add(1, 2), mul(2, 2)));
  print(mul(add(1, 2), add(3, 4)));
  return 0;
}
