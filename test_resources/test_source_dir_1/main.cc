#include "sample.h"
#include "hello/hello.h"

int main() {
    sample::Foo foo(std::vector<int>{1, 2, 3});
    foo.Print();
    hello();
}
