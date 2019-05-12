#include <iostream>
#include <vector>

namespace sample {


/**
 * Sample class declaration
 */
class Foo {
 public:
  explicit Foo(/*test*/std::vector<int> numbers): numbers_(numbers) {}

  void Print() const { printf("Ham"); }
 private:
  std::vector<int> numbers_;
};


}  // namespace sample
