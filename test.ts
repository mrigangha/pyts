function test(b, c) {
  let a: i32 = 100;
  while (a > b) {
    if (a < c) {
      print("A is less than 50");
    } else {
      print("A is greater than or equal to 50");
    }
    let a: i32 = a - 1;
  }
}
function main() {
  let b: i32 = 50;
  test(b, 100);
}
