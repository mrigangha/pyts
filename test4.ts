function test(b, c) {
  let a: i32 = 100;
  while (a > c) {
    if (a < b) {
      print("A is less than 50");
      print(a);
    } else {
      print("A is greater than or equal to 50");
      print(a);
    }
    let a: i32 = a - 1;
  }
  return 0;
}
function main() {
  let b: i32 = 50;
  test(b, 0);
  return 0;
}
