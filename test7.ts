function fact(n) {
  if (n <= 1) {
    return 1;
  } else {
    return n * fact(n - 1);
  }
  return 0;
}
function fib(n) {
  if (n <= 1) {
    return n;
  } else {
    return fib(n - 1) + fib(n - 2);
  }
  return 0;
}
function main() {
  print(fact(5));
  print(fact(0));
  print(fib(10));
  let x: i32 = fact(3) + fib(6);
  print(x);
  return 0;
}
