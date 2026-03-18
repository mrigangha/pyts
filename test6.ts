function test(b, c) {
  let a: i32 = 100;
  while (a > b) {
    print(a);
    let a: i32 = a - 1;
  }
  return 0;
}
function main() {
  let b: i32 = 50;
  test(b, 100);
  return 0;
}
