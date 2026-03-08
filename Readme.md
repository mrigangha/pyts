# A compiler implementation

It uses a simple lexer and A top down parser with llvm for codegen backend
Underdevelopment

one python file

## Demo Program

Example program that currently runs on the compiler:

```text
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
