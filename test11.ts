function isPositive(n: i32): bool {
  return n > 0;
}
function both(a: bool, b: bool): bool {
  return a && b;
}
function main() {
  let a: bool = true;
  let b: bool = false;
  print(a);
  print(!a);
  print(a || b);
  print(isPositive(5));
  print(isPositive(-3));
  print(both(true, true));
  if (a && isPositive(42)) {
    print("branch true");
  } else {
    print("branch false");
  }
  let x: i32 = 5;
  while (x > 0 && a) {
    print(x);
    x = x - 4;
  }
  return 0;
}
