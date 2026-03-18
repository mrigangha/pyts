function max(a, b): number {
  if (a > b) {
    return a;
  } else {
    return b;
  }
  return 0;
}

function main() {
  let a: i32 = 4;
  let c: i32 = (max(a, 2) / 2) * a;
  print(c);
  return 0;
}
