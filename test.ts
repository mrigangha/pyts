function main() {
  let a: i32 = 100;
  let b: i32 = 0;
  let c: i32 = 50;
  while (a > b) {
    if (a < c) {
      print("A is less than 50");
    } else {
      print("A is greater than or equal to 50");
    }
    let a: i32 = a - 1;
  }
}
