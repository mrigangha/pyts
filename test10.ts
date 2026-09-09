function greet(name: str): str {
  return "hi " + name;
}
function main() {
  let s: str = "hello";
  print(s);
  print(strlen(s));
  print(len(s));
  let t: str = "world";
  print(strcmp(s, t));
  print(strcmp(s, s));
  if (s == s) {
    print("self eq");
  }
  if (s != t) {
    print("ne ok");
  }
  let c: str = s + " " + t;
  print(c);
  print(greet("bob"));
  let buf: str = alloc(64);
  strcpy(buf, "abc");
  strcat(buf, "def");
  print(buf);
  print(strlen(buf));
  return 0;
}
