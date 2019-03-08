#include <vector>

namespace sample {

static const bool kSomeBool = 4 < 5;


/**
 * Sample class declaration
 */
class Foo {
 public:
  explicit Foo(/*test*/std::vector<int> numbers): numbers_(numbers) {}

  void Print() const;
 private:
  std::vector<int> numbers_;
};


/**
 * Irrelevant, added function declaration.
 */
void RedHerring();


}  // namespace sample
