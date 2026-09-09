function isEven(n) {
  if (n == 0) {
    return 1;
  } else {
    return isOdd(n - 1);
  }
  return 0;
}
function isOdd(n) {
  if (n == 0) {
    return 0;
  } else {
    return isEven(n - 1);
  }
  return 0;
}
function countdown(n) {
  if (n <= 0) {
    return 0;
  } else {
    print(n);
    return countdown(n - 1);
  }
  return 0;
}
function main() {
  print(isEven(10));
  print(isOdd(10));
  print(isEven(7));
  countdown(5);
  return 0;
}
